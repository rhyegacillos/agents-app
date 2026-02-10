#!/usr/bin/env bash
set -euo pipefail

# Creates/updates and attaches an IAM policy for GitHub Actions OIDC deploys.
# This grants Terraform read access to EC2 metadata, ECR push permissions, and SSM SendCommand
# used by .github/workflows/deploy-ec2.yml.
#
# Usage:
#   ./scripts/aws-iam-setup-gha-deploy-role.sh <ROLE_NAME_OR_ARN>
#
# Examples:
#   ./scripts/aws-iam-setup-gha-deploy-role.sh github-actions-digital-assistant-deploy
#   ./scripts/aws-iam-setup-gha-deploy-role.sh arn:aws:iam::348375262167:role/github-actions-digital-assistant-deploy
#
# Optional env:
#   POLICY_NAME=autonomous-trader-gha-deploy

if ! command -v aws >/dev/null 2>&1; then
  echo "ERROR: aws CLI is required." >&2
  exit 1
fi

ROLE_INPUT="${1:-${ROLE_NAME_OR_ARN:-${AWS_ROLE_ARN:-}}}"
if [[ -z "${ROLE_INPUT}" ]]; then
  echo "ERROR: Provide ROLE_NAME or ROLE_ARN as arg 1 (or set AWS_ROLE_ARN)." >&2
  exit 1
fi

# Accept either role name or role ARN.
ROLE_NAME="${ROLE_INPUT##*/}"

POLICY_NAME="${POLICY_NAME:-autonomous-trader-gha-deploy}"
INLINE_POLICY_NAME="${INLINE_POLICY_NAME:-${POLICY_NAME}-inline}"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
POLICY_ARN="arn:aws:iam::${ACCOUNT_ID}:policy/${POLICY_NAME}"

tmp_policy="$(mktemp)"
cleanup() { rm -f "${tmp_policy}"; }
trap cleanup EXIT

cat > "${tmp_policy}" <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TerraformEC2Read",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeImages",
        "ec2:DescribeInstanceTypes",
        "ec2:DescribeInstances",
        "ec2:DescribeVpcs",
        "ec2:DescribeSubnets",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeSecurityGroupRules"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ECRPush",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:CreateRepository",
        "ecr:DescribeRepositories",
        "ecr:BatchCheckLayerAvailability",
        "ecr:BatchGetImage",
        "ecr:CompleteLayerUpload",
        "ecr:InitiateLayerUpload",
        "ecr:PutImage",
        "ecr:UploadLayerPart"
      ],
      "Resource": "*"
    },
    {
      "Sid": "SSMRedeploy",
      "Effect": "Allow",
      "Action": [
        "ssm:SendCommand",
        "ssm:GetCommandInvocation",
        "ssm:ListCommandInvocations"
      ],
      "Resource": "*"
    },
    {
      "Sid": "STSRead",
      "Effect": "Allow",
      "Action": ["sts:GetCallerIdentity"],
      "Resource": "*"
    }
  ]
}
JSON

echo "Role: ${ROLE_NAME}"
echo "Policy: ${POLICY_ARN}"

if aws iam get-policy --policy-arn "${POLICY_ARN}" >/dev/null 2>&1; then
  echo "Policy exists; updating default policy version..."

  # IAM policies support up to 5 versions. If we are at limit, delete oldest non-default versions.
  versions_json="$(aws iam list-policy-versions --policy-arn "${POLICY_ARN}" --output json)"
  versions_count="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('Versions',[])))" <<<"${versions_json}")"
  if [[ "${versions_count}" -ge 5 ]]; then
    # Delete oldest non-default versions until under the limit.
    python3 - <<'PY' "${POLICY_ARN}" <<<"${versions_json}"
import json
import subprocess
import sys
from datetime import datetime, timezone

policy_arn = sys.argv[1]
data = json.load(sys.stdin)
versions = data.get("Versions", [])
non_default = [v for v in versions if not v.get("IsDefaultVersion")]

def parse_dt(s: str) -> datetime:
    # AWS returns ISO8601 with timezone, but python can parse via fromisoformat in many cases.
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)

non_default.sort(key=lambda v: parse_dt(v.get("CreateDate", "")))
while len(versions) >= 5 and non_default:
    v = non_default.pop(0)
    vid = v.get("VersionId")
    if not vid:
        continue
    subprocess.check_call(["aws", "iam", "delete-policy-version", "--policy-arn", policy_arn, "--version-id", vid])
    versions.pop()
PY
  fi

  aws iam create-policy-version \
    --policy-arn "${POLICY_ARN}" \
    --policy-document "file://${tmp_policy}" \
    --set-as-default \
    >/dev/null
else
  echo "Policy does not exist; creating..."
  aws iam create-policy \
    --policy-name "${POLICY_NAME}" \
    --policy-document "file://${tmp_policy}" \
    >/dev/null
fi

attached="$(aws iam list-attached-role-policies --role-name "${ROLE_NAME}" \
  --query "AttachedPolicies[?PolicyArn=='${POLICY_ARN}'].PolicyArn | [0]" --output text 2>/dev/null || true)"

attached_count="$(aws iam list-attached-role-policies --role-name "${ROLE_NAME}" --query "length(AttachedPolicies)" --output text 2>/dev/null || echo 0)"

if [[ "${attached}" == "${POLICY_ARN}" ]]; then
  echo "Managed policy already attached to role."
elif [[ "${attached_count}" -ge 10 ]]; then
  echo "Role already has ${attached_count} attached managed policies (AWS quota is 10)."
  echo "Falling back to an inline policy: ${INLINE_POLICY_NAME}"
  aws iam put-role-policy --role-name "${ROLE_NAME}" --policy-name "${INLINE_POLICY_NAME}" --policy-document "file://${tmp_policy}"
else
  echo "Attaching managed policy to role..."
  set +e
  attach_out="$(aws iam attach-role-policy --role-name "${ROLE_NAME}" --policy-arn "${POLICY_ARN}" 2>&1)"
  rc=$?
  set -e
  if [[ $rc -ne 0 ]]; then
    if echo "${attach_out}" | grep -q "PoliciesPerRole"; then
      echo "Attach failed due to managed policy quota. Falling back to inline policy: ${INLINE_POLICY_NAME}"
      aws iam put-role-policy --role-name "${ROLE_NAME}" --policy-name "${INLINE_POLICY_NAME}" --policy-document "file://${tmp_policy}"
    else
      echo "ERROR: Failed to attach policy to role:" >&2
      echo "${attach_out}" >&2
      exit $rc
    fi
  fi
fi

echo "Done."
