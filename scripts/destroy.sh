#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

fail() {
  log "ERROR: $*"
  exit 1
}

read_tfvars_value() {
  local tfvars_file="$1"
  local key="$2"

  awk -F= -v key="${key}" '
    $0 ~ "^[[:space:]]*" key "[[:space:]]*=" {
      value = substr($0, index($0, "=") + 1)
      sub(/^[[:space:]]+/, "", value)
      sub(/[[:space:]]+$/, "", value)
      gsub(/"/, "", value)
      print value
      exit
    }
  ' "${tfvars_file}"
}

bootstrap_tf_backend() {
  local project_name="$1"
  local aws_region="$2"
  local account_id
  local bucket_name
  local lock_table_name

  account_id="$(aws sts get-caller-identity --query 'Account' --output text)"
  bucket_name="${project_name}-terraform-state-${account_id}-${aws_region}"
  lock_table_name="${project_name}-terraform-locks"

  if ! aws s3api head-bucket --bucket "${bucket_name}" >/dev/null 2>&1; then
    if [[ "${aws_region}" == "us-east-1" ]]; then
      aws s3api create-bucket --bucket "${bucket_name}" >/dev/null
    else
      aws s3api create-bucket \
        --bucket "${bucket_name}" \
        --region "${aws_region}" \
        --create-bucket-configuration "LocationConstraint=${aws_region}" >/dev/null
    fi
  fi

  aws s3api put-bucket-versioning \
    --bucket "${bucket_name}" \
    --versioning-configuration Status=Enabled >/dev/null

  aws s3api put-bucket-encryption \
    --bucket "${bucket_name}" \
    --server-side-encryption-configuration '{
      "Rules": [
        {
          "ApplyServerSideEncryptionByDefault": {
            "SSEAlgorithm": "AES256"
          },
          "BucketKeyEnabled": true
        }
      ]
    }' >/dev/null

  aws s3api put-public-access-block \
    --bucket "${bucket_name}" \
    --public-access-block-configuration \
      BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true >/dev/null

  if ! aws dynamodb describe-table --table-name "${lock_table_name}" --region "${aws_region}" >/dev/null 2>&1; then
    aws dynamodb create-table \
      --table-name "${lock_table_name}" \
      --region "${aws_region}" \
      --attribute-definitions AttributeName=LockID,AttributeType=S \
      --key-schema AttributeName=LockID,KeyType=HASH \
      --billing-mode PAY_PER_REQUEST >/dev/null

    aws dynamodb wait table-exists \
      --table-name "${lock_table_name}" \
      --region "${aws_region}"
  fi

  TF_BACKEND_BUCKET="${bucket_name}"
  TF_BACKEND_DDB_TABLE="${lock_table_name}"
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
PROJECT_NAME="medinotes"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-ap-southeast-1}}"
TF_DIR="terraform"
TFVARS_FILE=""
TFVARS_NAME=""

if [[ -z "${ENVIRONMENT}" ]]; then
  echo "Usage: $0 <dev|prod>" >&2
  exit 1
fi

case "${ENVIRONMENT}" in
  dev|prod)
    ;;
  *)
    fail "Invalid environment: ${ENVIRONMENT}. Use one of: dev, prod."
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

TFVARS_ENVIRONMENT="$(read_tfvars_value "${TFVARS_FILE}" environment)"
TFVARS_PROJECT_NAME="$(read_tfvars_value "${TFVARS_FILE}" project_name)"
TFVARS_AWS_REGION="$(read_tfvars_value "${TFVARS_FILE}" aws_region)"

if [[ -n "${TFVARS_ENVIRONMENT}" && "${TFVARS_ENVIRONMENT}" != "${ENVIRONMENT}" ]]; then
  fail "Environment mismatch: requested '${ENVIRONMENT}' but ${TFVARS_FILE} is set to '${TFVARS_ENVIRONMENT}'."
fi

if [[ -n "${TFVARS_PROJECT_NAME}" && "${PROJECT_NAME}" != "${TFVARS_PROJECT_NAME}" ]]; then
  if [[ "${PROJECT_NAME}" == "medinotes" ]]; then
    PROJECT_NAME="${TFVARS_PROJECT_NAME}"
  else
    fail "Project name mismatch: requested '${PROJECT_NAME}' but ${TFVARS_FILE} is set to '${TFVARS_PROJECT_NAME}'."
  fi
fi

if [[ -n "${TFVARS_AWS_REGION}" && "${AWS_REGION}" != "${TFVARS_AWS_REGION}" ]]; then
  if [[ "${AWS_REGION}" == "ap-southeast-1" ]]; then
    AWS_REGION="${TFVARS_AWS_REGION}"
  else
    fail "AWS region mismatch: requested '${AWS_REGION}' but ${TFVARS_FILE} is set to '${TFVARS_AWS_REGION}'."
  fi
fi

export AWS_REGION
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-${AWS_REGION}}"

log "Bootstrapping Terraform backend for ${PROJECT_NAME} in ${AWS_REGION}"
bootstrap_tf_backend "${PROJECT_NAME}" "${AWS_REGION}"

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

empty_ecr_repository "${PROJECT_NAME}-${ENVIRONMENT}-app"

log "Destroying all Terraform-managed resources for ${ENVIRONMENT}"
terraform -chdir="${TF_DIR}" destroy -auto-approve \
  -var-file="${TFVARS_NAME}"

log "Destroy completed for ${ENVIRONMENT}"
