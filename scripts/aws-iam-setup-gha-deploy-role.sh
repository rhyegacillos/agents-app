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
#   GITHUB_OWNER=rhyegacillos
#   GITHUB_REPO=agents-app
#   GITHUB_BRANCH=autonomous-trader-agent-aws
#   GITHUB_ENVIRONMENTS=dev,prod   (recommended if your workflow uses `environment:`)
#   GITHUB_SUBJECTS=<comma-separated "sub" patterns>  (advanced override)

if ! command -v aws >/dev/null 2>&1; then
  echo "ERROR: aws CLI is required." >&2
  exit 1
fi

ROLE_INPUT="${1:-${ROLE_NAME_OR_ARN:-${AWS_ROLE_ARN_TRADER:-${AWS_ROLE_ARN:-}}}}"
if [[ -z "${ROLE_INPUT}" ]]; then
  echo "ERROR: Provide ROLE_NAME or ROLE_ARN as arg 1 (or set AWS_ROLE_ARN_TRADER / AWS_ROLE_ARN)." >&2
  exit 1
fi

# Accept either role name or role ARN.
ROLE_NAME="${ROLE_INPUT##*/}"

POLICY_NAME="${POLICY_NAME:-autonomous-trader-gha-deploy}"
INLINE_POLICY_NAME="${INLINE_POLICY_NAME:-${POLICY_NAME}-inline}"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
POLICY_ARN="arn:aws:iam::${ACCOUNT_ID}:policy/${POLICY_NAME}"

# Ensure the role exists and has a GitHub OIDC trust policy.
# This keeps setup portable: you can point it at a new role name and it will
# be created correctly for this repo/branch.
GITHUB_OWNER="${GITHUB_OWNER:-rhyegacillos}"
GITHUB_REPO="${GITHUB_REPO:-agents-app}"
GITHUB_BRANCH="${GITHUB_BRANCH:-autonomous-trader-agent-aws}"

# GitHub OIDC `sub` depends on workflow context:
# - branch push: repo:OWNER/REPO:ref:refs/heads/BRANCH
# - if job uses `environment: <name>`: repo:OWNER/REPO:environment:<name>
#
# Our deploy workflow uses environments, so allow both patterns by default.
GITHUB_ENVIRONMENTS="${GITHUB_ENVIRONMENTS:-dev,prod}"

default_subjects="repo:${GITHUB_OWNER}/${GITHUB_REPO}:ref:refs/heads/${GITHUB_BRANCH}"
if [[ -n "${GITHUB_ENVIRONMENTS}" ]]; then
  IFS=',' read -r -a _envs <<<"${GITHUB_ENVIRONMENTS}"
  for e in "${_envs[@]}"; do
    e="${e#"${e%%[![:space:]]*}"}"
    e="${e%"${e##*[![:space:]]}"}"
    [[ -z "${e}" ]] && continue
    default_subjects+=",repo:${GITHUB_OWNER}/${GITHUB_REPO}:environment:${e}"
  done
fi

GITHUB_SUBJECTS="${GITHUB_SUBJECTS:-${default_subjects}}"

OIDC_PROVIDER_ARN="arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"

ensure_oidc_provider() {
  if aws iam get-open-id-connect-provider --open-id-connect-provider-arn "${OIDC_PROVIDER_ARN}" >/dev/null 2>&1; then
    return 0
  fi
  echo "GitHub OIDC provider not found; creating: ${OIDC_PROVIDER_ARN}"
  # GitHub's current root CA thumbprint commonly used for the Actions OIDC provider.
  # If AWS rejects this in the future, create it once in the console and rerun this script.
  aws iam create-open-id-connect-provider \
    --url "https://token.actions.githubusercontent.com" \
    --client-id-list "sts.amazonaws.com" \
    --thumbprint-list "6938fd4d98bab03faadb97b34396831e3780aea1" \
    >/dev/null
}

ensure_role_with_trust() {
  local tmp_trust
  tmp_trust="$(mktemp)"

  # Convert comma-separated subject patterns into a JSON array for the trust policy.
  local sub_json
  sub_json="$(python3 -c 'import json,sys
vals=[s.strip() for s in sys.argv[1].split(",") if s.strip()]
print(json.dumps(vals))
' "${GITHUB_SUBJECTS}")"

  cat > "${tmp_trust}" <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "${OIDC_PROVIDER_ARN}"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": ${sub_json}
        }
      }
    }
  ]
}
JSON

  if aws iam get-role --role-name "${ROLE_NAME}" >/dev/null 2>&1; then
    # Keep trust aligned (safe idempotent update).
    aws iam update-assume-role-policy \
      --role-name "${ROLE_NAME}" \
      --policy-document "file://${tmp_trust}" \
      >/dev/null
  else
    aws iam create-role \
      --role-name "${ROLE_NAME}" \
      --assume-role-policy-document "file://${tmp_trust}" \
      --description "GitHub Actions OIDC deploy role for autonomous-trader" \
      >/dev/null
  fi
  rm -f "${tmp_trust}"
}

ensure_oidc_provider
ensure_role_with_trust

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
        "ec2:Describe*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "TerraformEC2SecurityGroupWrite",
      "Effect": "Allow",
      "Action": [
        "ec2:AuthorizeSecurityGroupIngress",
        "ec2:RevokeSecurityGroupIngress",
        "ec2:AuthorizeSecurityGroupEgress",
        "ec2:RevokeSecurityGroupEgress"
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
      "Sid": "Route53Optional",
      "Effect": "Allow",
      "Action": [
        "route53:ChangeResourceRecordSets",
        "route53:GetChange",
        "route53:GetHostedZone",
        "route53:ListHostedZones",
        "route53:ListHostedZonesByName",
        "route53:ListResourceRecordSets"
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
    # IMPORTANT: don't use `python3 -` here (stdin is the code). We need stdin for JSON.
    python3 -c 'import json,subprocess,sys
from datetime import datetime, timezone

policy_arn = sys.argv[1]
data = json.load(sys.stdin)
versions = data.get("Versions", [])
non_default = [v for v in versions if not v.get("IsDefaultVersion")]

def parse_dt(s: str) -> datetime:
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
' "${POLICY_ARN}" <<<"${versions_json}"
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
