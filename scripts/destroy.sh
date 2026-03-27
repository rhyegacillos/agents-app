#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

fail() {
  log "ERROR: $*"
  exit 1
}

empty_ecr_repository() {
  local repository_name="$1"
  local image_digests_text
  local -a image_digests=()
  local digest
  local attempt

  if ! aws ecr describe-repositories --repository-names "${repository_name}" >/dev/null 2>&1; then
    log "ECR repository ${repository_name} does not exist. Skipping image cleanup."
    return 0
  fi

  for attempt in $(seq 1 5); do
    image_digests=()
    image_digests_text="$(aws ecr list-images \
      --repository-name "${repository_name}" \
      --query 'imageIds[].imageDigest' \
      --output text)"

    if [[ -z "${image_digests_text}" || "${image_digests_text}" == "None" ]]; then
      log "ECR repository ${repository_name} is empty."
      return 0
    fi

    while IFS= read -r digest; do
      [[ -n "${digest}" && "${digest}" != "None" ]] && image_digests+=("${digest}")
    done < <(printf '%s\n' "${image_digests_text}" | tr '\t' '\n')

    if [[ ${#image_digests[@]} -eq 0 ]]; then
      log "ECR repository ${repository_name} is empty."
      return 0
    fi

    log "Deleting ${#image_digests[@]} image digests from ECR repository ${repository_name} (attempt ${attempt}/5)"
    for digest in "${image_digests[@]}"; do
      delete_output="$(aws ecr batch-delete-image \
        --repository-name "${repository_name}" \
        --image-ids "imageDigest=${digest}")"
      if [[ "${delete_output}" != *'"failures": []'* ]]; then
        printf '%s\n' "${delete_output}" >&2
        fail "Failed deleting one or more images from ${repository_name}"
      fi
    done

    sleep 2
  done

  fail "ECR repository ${repository_name} still contains images after cleanup attempts"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENVIRONMENT="${1:-}"
PROJECT_NAME="ideagen"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-ap-southeast-1}}"
TF_DIR="terraform"
TFVARS_FILE=""
TFVARS_NAME=""

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

if [[ "${TFVARS_FILE}" != /* ]]; then
  TFVARS_FILE="${REPO_ROOT}/${TFVARS_FILE}"
fi

if [[ ! -f "${TFVARS_FILE}" ]]; then
  fail "Terraform var-file not found: ${TFVARS_FILE}"
fi

TFVARS_NAME="$(basename "${TFVARS_FILE}")"

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

if terraform -chdir="${TF_DIR}" state show aws_db_instance.postgres >/dev/null 2>&1; then
  log "Disabling RDS deletion protection before destroy"
  terraform -chdir="${TF_DIR}" apply -auto-approve \
    -var-file="${TFVARS_NAME}" \
    -var="db_deletion_protection=false" \
    -target=aws_db_instance.postgres
fi

empty_ecr_repository "${PROJECT_NAME}-${ENVIRONMENT}-app"

log "Destroying all Terraform-managed resources for ${ENVIRONMENT}"
terraform -chdir="${TF_DIR}" destroy -auto-approve \
  -var-file="${TFVARS_NAME}" \
  -var="db_deletion_protection=false"

log "Destroy completed for ${ENVIRONMENT}"
