#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="${SCRIPT_DIR}/../terraform"

if [[ ! -d "${TF_DIR}" ]]; then
  echo "Terraform directory not found at ${TF_DIR}" >&2
  exit 1
fi

if [[ -f "${TF_DIR}/terraform.tfvars.local" ]]; then
  cp "${TF_DIR}/terraform.tfvars.local" "${TF_DIR}/terraform.tfvars"
fi

if [[ ! -f "${TF_DIR}/terraform.tfvars" ]]; then
  echo "Missing terraform/terraform.tfvars. Create terraform/terraform.tfvars.local first." >&2
  exit 1
fi

cd "${TF_DIR}"
# Avoid double-init spam when called from terraform-deploy.sh.
if [[ ! -d ".terraform" ]]; then
  terraform init -input=false
fi

read_tfvar() {
  local key="$1"
  local raw
  raw=$(awk -F= -v k="$key" '$1 ~ "^[ \t]*"k"[ \t]*$" {print $2}' terraform.tfvars | tail -n1)
  raw="${raw#"${raw%%[![:space:]]*}"}"
  raw="${raw%"${raw##*[![:space:]]}"}"
  raw="${raw%\"}"; raw="${raw#\"}"
  raw="${raw%\'}"; raw="${raw#\'}"
  echo "$raw"
}

sg_id="$(read_tfvar existing_security_group_id)"
instance_id="$(read_tfvar existing_instance_id)"
ssh_cidr="$(read_tfvar allowed_ssh_cidr)"

if [[ -z "${ssh_cidr}" ]]; then
  ssh_cidr="0.0.0.0/0"
fi

if [[ -z "${sg_id}" ]]; then
  if [[ -n "${instance_id}" ]] && command -v aws >/dev/null 2>&1; then
    sg_id="$(aws ec2 describe-instances --instance-ids "${instance_id}" \
      --query "Reservations[].Instances[].SecurityGroups[0].GroupId" --output text 2>/dev/null)"
  fi
fi

if [[ -z "${sg_id}" || "${sg_id}" == "None" ]]; then
  echo "Unable to resolve existing_security_group_id. Set it in terraform.tfvars.local." >&2
  exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "AWS CLI not found. Install and configure it before running this script." >&2
  exit 1
fi

get_rule_id() {
  local port="$1"
  local cidr="$2"
  aws ec2 describe-security-group-rules \
    --filters Name=group-id,Values="${sg_id}" \
    --query "SecurityGroupRules[?IsEgress==\`false\` && FromPort==\`${port}\` && ToPort==\`${port}\` && IpProtocol=='tcp' && CidrIpv4=='${cidr}'].SecurityGroupRuleId | [0]" \
    --output text 2>/dev/null
}

get_any_rule_cidrs_for_port() {
  local port="$1"
  aws ec2 describe-security-group-rules \
    --filters Name=group-id,Values="${sg_id}" \
    --query "SecurityGroupRules[?IsEgress==\`false\` && FromPort==\`${port}\` && ToPort==\`${port}\` && IpProtocol=='tcp'].CidrIpv4" \
    --output text 2>/dev/null | tr '\t' '\n' | sed '/^None$/d' | sort -u
}

import_rule() {
  local tf_resource="$1"
  local rule_id="$2"
  local _unused="$3"

  get_state_id() {
    local addr="$1"
    # Avoid provider schema loading; parse state directly.
    python3 - "$addr" <<-'PY'
import json
import subprocess
import sys

addr = sys.argv[1]
state = subprocess.check_output(["terraform", "state", "pull"], text=True)
data = json.loads(state)

for r in data.get("resources", []):
    name = r.get("name")
    t = r.get("type")
    for inst in r.get("instances", []):
        idx = inst.get("index_key")
        base = f"{t}.{name}"
        full = f"{base}[{idx}]" if idx is not None else base
        if full == addr:
            attrs = inst.get("attributes") or {}
            v = attrs.get("id") or attrs.get("security_group_rule_id") or ""
            print(v)
            sys.exit(0)

print("")
PY
  }

  # Important: use fixed-string matching. Terraform addresses include "[0]" which
  # is a regex character class in grep, so plain grep can give false negatives.
  if terraform state list 2>/dev/null | grep -Fqx "${tf_resource}"; then
    # If state points at a different remote rule than the one we detected,
    # drop it and re-import the correct rule_id.
    if [[ -n "${rule_id}" && "${rule_id}" != "None" ]]; then
      current_id="$(get_state_id "${tf_resource}")"
      if [[ -n "${current_id}" && "${current_id}" != "${rule_id}" ]]; then
        echo "State mismatch for ${tf_resource}: state=${current_id} detected=${rule_id}; re-importing"
        terraform state rm "${tf_resource}" >/dev/null 2>&1 || true
      else
        echo "Already imported: ${tf_resource}"
        return 0
      fi
    else
      echo "Already imported: ${tf_resource}"
      return 0
    fi
  fi

  if [[ -z "${rule_id}" || "${rule_id}" == "None" ]]; then
    echo "Rule not found for ${tf_resource}; Terraform will create it on apply if needed."
    return 0
  fi

  # We use aws_vpc_security_group_ingress_rule, which imports cleanly with sgr-... IDs.
  local out=""
  if out="$(terraform import "${tf_resource}" "${rule_id}" 2>&1)"; then
    echo "Imported: ${tf_resource} (${rule_id})"
    return 0
  fi

  echo "Failed to import ${tf_resource}. Try importing manually." >&2
  echo "Tried IDs:" >&2
  echo "  - ${rule_id}" >&2
  echo "Terraform import error:" >&2
  echo "${out}" | sed 's/^/  /' >&2
  return 1
}

http_rule_id="$(get_rule_id 80 "0.0.0.0/0")"
https_rule_id="$(get_rule_id 443 "0.0.0.0/0")"
ssh_rule_id="$(get_rule_id 22 "${ssh_cidr}")"

# If we can't find an exact match but there are rules on that port already,
# stop here so Terraform doesn't attempt a create that will likely fail as a duplicate.
if [[ -z "${http_rule_id}" || "${http_rule_id}" == "None" ]]; then
  any_http="$(get_any_rule_cidrs_for_port 80 || true)"
  if [[ -n "${any_http}" ]]; then
    echo "ERROR: Found existing 80/tcp ingress CIDRs on ${sg_id}, but none match 0.0.0.0/0:" >&2
    echo "${any_http}" | sed 's/^/  - /' >&2
    exit 1
  fi
fi

if [[ -z "${https_rule_id}" || "${https_rule_id}" == "None" ]]; then
  any_https="$(get_any_rule_cidrs_for_port 443 || true)"
  if [[ -n "${any_https}" ]]; then
    echo "ERROR: Found existing 443/tcp ingress CIDRs on ${sg_id}, but none match 0.0.0.0/0:" >&2
    echo "${any_https}" | sed 's/^/  - /' >&2
    exit 1
  fi
fi

if [[ -z "${ssh_rule_id}" || "${ssh_rule_id}" == "None" ]]; then
  any_ssh="$(get_any_rule_cidrs_for_port 22 || true)"
  if [[ -n "${any_ssh}" ]]; then
    echo "ERROR: Found existing 22/tcp ingress CIDRs on ${sg_id}, but none match ${ssh_cidr}." >&2
    echo "Set allowed_ssh_cidr in terraform/terraform.tfvars.local to one of:" >&2
    echo "${any_ssh}" | sed 's/^/  - /' >&2
    exit 1
  fi
fi

# If you previously used legacy aws_security_group_rule resources, remove them from state
# so they don't conflict with aws_vpc_security_group_ingress_rule imports.
while IFS= read -r legacy; do
  [[ -z "${legacy}" ]] && continue
  terraform state rm "${legacy}" >/dev/null 2>&1 || true
done < <(terraform state list 2>/dev/null | awk '/^aws_security_group_rule\\.existing_/ {print}')

# These resources are declared with count, so the correct addresses include [0].
import_rule "aws_vpc_security_group_ingress_rule.existing_http[0]" "${http_rule_id}" ""
import_rule "aws_vpc_security_group_ingress_rule.existing_https[0]" "${https_rule_id}" ""
import_rule "aws_vpc_security_group_ingress_rule.existing_ssh[0]" "${ssh_rule_id}" ""

echo "Done. Run 'terraform plan' to confirm."
