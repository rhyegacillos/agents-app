#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

fail() {
  log "ERROR: $*"
  exit 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENVIRONMENT="${1:-}"
PROJECT_NAME="ideagen"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-ap-southeast-1}}"
TF_DIR="terraform"
TFVARS_FILE=""

if [[ -z "${ENVIRONMENT}" ]]; then
  echo "Usage: $0 <dev|test|prod>" >&2
  exit 1
fi

case "${ENVIRONMENT}" in
  dev|test|prod)
    ;;
  *)
    fail "Invalid environment: ${ENVIRONMENT}. Use one of: dev, test, prod."
    ;;
esac

shift || true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-name)
      PROJECT_NAME="$2"
      shift 2
      ;;
    --region)
      AWS_REGION="$2"
      shift 2
      ;;
    --terraform-dir)
      TF_DIR="$2"
      shift 2
      ;;
    --tfvars-file)
      TFVARS_FILE="$2"
      shift 2
      ;;
    *)
      fail "Unknown argument: $1"
      ;;
  esac
done

if [[ -z "${TFVARS_FILE}" ]]; then
  TFVARS_FILE="${TF_DIR}/${ENVIRONMENT}.tfvars"
fi

if [[ ! -f "${TFVARS_FILE}" ]]; then
  fail "Terraform var-file not found: ${TFVARS_FILE}"
fi

TFVARS_ENVIRONMENT="$(awk -F= '/^[[:space:]]*environment[[:space:]]*=/{gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); gsub(/"/, "", $2); print $2; exit}' "${TFVARS_FILE}")"
if [[ -n "${TFVARS_ENVIRONMENT}" && "${TFVARS_ENVIRONMENT}" != "${ENVIRONMENT}" ]]; then
  fail "Environment mismatch: requested '${ENVIRONMENT}' but ${TFVARS_FILE} is set to '${TFVARS_ENVIRONMENT}'."
fi

export AWS_REGION
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-${AWS_REGION}}"

log "Bootstrapping Terraform backend for ${PROJECT_NAME} in ${AWS_REGION}"
BACKEND_OUTPUT="$("${SCRIPT_DIR}/bootstrap_tf_backend.sh" \
  --project-name "${PROJECT_NAME}" \
  --region "${AWS_REGION}")"

TF_BACKEND_BUCKET="$(printf '%s\n' "${BACKEND_OUTPUT}" | awk -F= '/^TF_BACKEND_BUCKET=/{print $2}')"
TF_BACKEND_DDB_TABLE="$(printf '%s\n' "${BACKEND_OUTPUT}" | awk -F= '/^TF_BACKEND_DDB_TABLE=/{print $2}')"

log "Initializing Terraform with backend bucket ${TF_BACKEND_BUCKET}"
terraform -chdir="${TF_DIR}" init \
  -reconfigure \
  -backend-config="bucket=${TF_BACKEND_BUCKET}" \
  -backend-config="dynamodb_table=${TF_BACKEND_DDB_TABLE}" \
  -backend-config="key=${PROJECT_NAME}/${ENVIRONMENT}/terraform.tfstate" \
  -backend-config="region=${AWS_REGION}"

log "Selecting Terraform workspace ${ENVIRONMENT}"
terraform -chdir="${TF_DIR}" workspace new "${ENVIRONMENT}" >/dev/null 2>&1 || true
terraform -chdir="${TF_DIR}" workspace select "${ENVIRONMENT}"

log "Destroying all Terraform-managed resources for ${ENVIRONMENT}"
terraform -chdir="${TF_DIR}" destroy -auto-approve -var-file="${TFVARS_FILE}"

log "Destroy completed for ${ENVIRONMENT}"
