#!/usr/bin/env bash
set -euo pipefail
umask 077

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

sync_runtime_secrets() {
  local project_name="$1"
  local environment="$2"
  local aws_region="$3"
  local secret_prefix="${project_name}-${environment}/app"
  local -a secret_temp_files=()

  for required in OPENAI_API_KEY GEMINI_API_KEY DEEPSEEK_API_KEY GROK_API_KEY RESEND_API_KEY CLERK_SECRET_KEY CLERK_JWKS_URL BRAVE_API_KEY UPSTASH_REDIS_REST_URL UPSTASH_REDIS_REST_TOKEN; do
    [[ -n "${!required:-}" ]] || fail "${required} is required."
  done

  cleanup_secret_files() {
    local temp_file
    for temp_file in "${secret_temp_files[@]}"; do
      [[ -f "${temp_file}" ]] && rm -f "${temp_file}"
    done
  }

  trap cleanup_secret_files RETURN

  upsert_secret() {
    local secret_name="$1"
    local secret_value="$2"
    local temp_file

    temp_file="$(mktemp)"
    secret_temp_files+=("${temp_file}")
    printf '%s' "${secret_value}" > "${temp_file}"

    if aws secretsmanager describe-secret --secret-id "${secret_name}" --region "${aws_region}" >/dev/null 2>&1; then
      aws secretsmanager put-secret-value \
        --secret-id "${secret_name}" \
        --region "${aws_region}" \
        --secret-string "file://${temp_file}" >/dev/null
    else
      aws secretsmanager create-secret \
        --name "${secret_name}" \
        --region "${aws_region}" \
        --secret-string "file://${temp_file}" >/dev/null
    fi
  }

  upsert_secret "${secret_prefix}/OPENAI_API_KEY" "${OPENAI_API_KEY}"
  upsert_secret "${secret_prefix}/GEMINI_API_KEY" "${GEMINI_API_KEY}"
  upsert_secret "${secret_prefix}/DEEPSEEK_API_KEY" "${DEEPSEEK_API_KEY}"
  upsert_secret "${secret_prefix}/GROK_API_KEY" "${GROK_API_KEY}"
  upsert_secret "${secret_prefix}/RESEND_API_KEY" "${RESEND_API_KEY}"
  upsert_secret "${secret_prefix}/CLERK_SECRET_KEY" "${CLERK_SECRET_KEY}"
  upsert_secret "${secret_prefix}/CLERK_JWKS_URL" "${CLERK_JWKS_URL}"
  upsert_secret "${secret_prefix}/BRAVE_API_KEY" "${BRAVE_API_KEY}"
  upsert_secret "${secret_prefix}/UPSTASH_REDIS_REST_URL" "${UPSTASH_REDIS_REST_URL}"
  upsert_secret "${secret_prefix}/UPSTASH_REDIS_REST_TOKEN" "${UPSTASH_REDIS_REST_TOKEN}"

  trap - RETURN
  cleanup_secret_files
}

wait_for_service_running() {
  local service_arn="$1"
  local aws_region="$2"
  local label="$3"

  for i in $(seq 1 60); do
    current_status="$(aws apprunner describe-service --service-arn "${service_arn}" --region "${aws_region}" --query 'Service.Status' --output text)"
    log "${label} ${i}/60: ${current_status}"
    if [[ "${current_status}" == "RUNNING" ]]; then
      return 0
    fi
    if [[ "${current_status}" != "OPERATION_IN_PROGRESS" && "${current_status}" != "CREATE_IN_PROGRESS" ]]; then
      fail "App Runner service is not ready: ${current_status}"
    fi
    sleep 10
  done

  fail "App Runner service did not become RUNNING in time"
}

build_and_push_image() {
  local ecr_repository_url="$1"
  local aws_region="$2"
  local image_sha="$3"

  [[ -n "${NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY:-}" ]] || fail "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is required."
  [[ -n "${NEXT_PUBLIC_CLERK_JWT_TEMPLATE:-}" ]] || fail "NEXT_PUBLIC_CLERK_JWT_TEMPLATE is required."

  aws ecr get-login-password --region "${aws_region}" | docker login --username AWS --password-stdin "${ecr_repository_url%/*}" >/dev/null

  log "Building Docker image"
  docker build \
    --build-arg "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=${NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY}" \
    --build-arg "NEXT_PUBLIC_CLERK_JWT_TEMPLATE=${NEXT_PUBLIC_CLERK_JWT_TEMPLATE}" \
    -t "${ecr_repository_url}:latest" \
    -t "${ecr_repository_url}:${image_sha}" \
    .

  log "Pushing Docker images to ECR"
  docker push "${ecr_repository_url}:latest"
  docker push "${ecr_repository_url}:${image_sha}"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

load_env_file() {
  local env_file="$1"
  if [[ -f "${env_file}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${env_file}"
    set +a
  fi
}

load_env_file "${REPO_ROOT}/.env"
load_env_file "${REPO_ROOT}/.env.local"

ENVIRONMENT="${1:-}"
PROJECT_NAME=""
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-}}"
TF_DIR="terraform"
TFVARS_FILE=""
IMAGE_SHA="${IMAGE_SHA:-${GITHUB_SHA:-manual}}"
INIT_ONLY="false"

if [[ -z "${ENVIRONMENT}" ]]; then
  echo "Usage: $0 <dev|prod> [--project-name <name>] [--region <region>] [--terraform-dir <dir>] [--tfvars-file <file>] [--image-sha <sha>] [--init-only]" >&2
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
    --image-sha)
      IMAGE_SHA="$2"
      shift 2
      ;;
    --init-only)
      INIT_ONLY="true"
      shift
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

[[ -f "${TFVARS_FILE}" ]] || fail "Terraform var-file not found: ${TFVARS_FILE}"

TFVARS_NAME="$(basename "${TFVARS_FILE}")"
TFVARS_ENVIRONMENT="$(read_tfvars_value "${TFVARS_FILE}" environment)"
TFVARS_PROJECT_NAME="$(read_tfvars_value "${TFVARS_FILE}" project_name)"
TFVARS_AWS_REGION="$(read_tfvars_value "${TFVARS_FILE}" aws_region)"

[[ "${TFVARS_ENVIRONMENT}" == "${ENVIRONMENT}" ]] || fail "Environment mismatch: requested '${ENVIRONMENT}' but ${TFVARS_FILE} is set to '${TFVARS_ENVIRONMENT}'."
[[ -n "${TFVARS_PROJECT_NAME}" ]] || fail "project_name is required in ${TFVARS_FILE}"
[[ -n "${TFVARS_AWS_REGION}" ]] || fail "aws_region is required in ${TFVARS_FILE}"

if [[ -n "${PROJECT_NAME}" && "${PROJECT_NAME}" != "${TFVARS_PROJECT_NAME}" ]]; then
  fail "Project name mismatch: requested '${PROJECT_NAME}' but ${TFVARS_FILE} is set to '${TFVARS_PROJECT_NAME}'."
fi

if [[ -n "${AWS_REGION}" && "${AWS_REGION}" != "${TFVARS_AWS_REGION}" ]]; then
  fail "AWS region mismatch: requested '${AWS_REGION}' but ${TFVARS_FILE} is set to '${TFVARS_AWS_REGION}'."
fi

PROJECT_NAME="${TFVARS_PROJECT_NAME}"
AWS_REGION="${TFVARS_AWS_REGION}"

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

if [[ "${INIT_ONLY}" == "true" ]]; then
  log "Terraform backend and workspace are ready for ${ENVIRONMENT}. Exiting due to --init-only."
  exit 0
fi

SERVICE_EXISTS="false"
SERVICE_ARN=""
SERVICE_URL=""
PRE_PUSH_UPDATED_AT=""

if terraform -chdir="${TF_DIR}" state show 'aws_apprunner_service.app[0]' >/dev/null 2>&1; then
  SERVICE_EXISTS="true"
  SERVICE_ARN="$(terraform -chdir="${TF_DIR}" output -raw app_runner_service_arn 2>/dev/null || true)"
  SERVICE_URL="$(terraform -chdir="${TF_DIR}" output -raw app_runner_service_url 2>/dev/null || true)"
fi

log "Bootstrapping prerequisite infrastructure"
terraform -chdir="${TF_DIR}" apply -auto-approve -var-file="${TFVARS_NAME}" \
  -target=aws_dynamodb_table.memory \
  -target=aws_ecr_repository.app \
  -target=aws_ecr_lifecycle_policy.app \
  -target=aws_iam_role.apprunner_ecr_access \
  -target=aws_iam_role_policy_attachment.apprunner_ecr_access \
  -target=aws_iam_role.apprunner_instance \
  -target=aws_iam_role_policy.apprunner_instance_runtime \
  -target=aws_apprunner_auto_scaling_configuration_version.main \
  -target=aws_secretsmanager_secret.openai_api_key \
  -target=aws_secretsmanager_secret.gemini_api_key \
  -target=aws_secretsmanager_secret.deepseek_api_key \
  -target=aws_secretsmanager_secret.grok_api_key \
  -target=aws_secretsmanager_secret.resend_api_key \
  -target=aws_secretsmanager_secret.clerk_secret_key \
  -target=aws_secretsmanager_secret.clerk_jwks_url \
  -target=aws_secretsmanager_secret.brave_api_key \
  -target=aws_secretsmanager_secret.upstash_redis_rest_url \
  -target=aws_secretsmanager_secret.upstash_redis_rest_token

ECR_REPOSITORY_URL="$(terraform -chdir="${TF_DIR}" output -raw ecr_repository_url)"

log "Syncing runtime secrets to AWS Secrets Manager"
sync_runtime_secrets "${PROJECT_NAME}" "${ENVIRONMENT}" "${AWS_REGION}"

if [[ "${SERVICE_EXISTS}" == "true" ]]; then
  log "Existing App Runner service detected. Applying Terraform before image push."
  terraform -chdir="${TF_DIR}" apply -auto-approve -var-file="${TFVARS_NAME}"
  SERVICE_ARN="$(terraform -chdir="${TF_DIR}" output -raw app_runner_service_arn)"
  SERVICE_URL="$(terraform -chdir="${TF_DIR}" output -raw app_runner_service_url)"
  wait_for_service_running "${SERVICE_ARN}" "${AWS_REGION}" "Pre-push App Runner status"
  PRE_PUSH_UPDATED_AT="$(aws apprunner describe-service --service-arn "${SERVICE_ARN}" --region "${AWS_REGION}" --query 'Service.UpdatedAt' --output text)"
fi

build_and_push_image "${ECR_REPOSITORY_URL}" "${AWS_REGION}" "${IMAGE_SHA}"

if [[ "${SERVICE_EXISTS}" != "true" ]]; then
  log "Creating App Runner service"
  terraform -chdir="${TF_DIR}" apply -auto-approve -var-file="${TFVARS_NAME}"
  SERVICE_ARN="$(terraform -chdir="${TF_DIR}" output -raw app_runner_service_arn)"
  SERVICE_URL="$(terraform -chdir="${TF_DIR}" output -raw app_runner_service_url)"
fi

[[ -n "${SERVICE_ARN}" ]] || fail "Missing App Runner service ARN."
[[ -n "${SERVICE_URL}" ]] || fail "Missing App Runner service URL."

log "Waiting for App Runner rollout and health"
SAW_ROLLOUT="false"
for i in $(seq 1 60); do
  CURRENT_STATUS="$(aws apprunner describe-service --service-arn "${SERVICE_ARN}" --region "${AWS_REGION}" --query 'Service.Status' --output text)"
  CURRENT_UPDATED_AT="$(aws apprunner describe-service --service-arn "${SERVICE_ARN}" --region "${AWS_REGION}" --query 'Service.UpdatedAt' --output text)"
  log "Service status ${i}/60: ${CURRENT_STATUS} (UpdatedAt=${CURRENT_UPDATED_AT})"

  if [[ -z "${PRE_PUSH_UPDATED_AT}" ]]; then
    if [[ "${CURRENT_STATUS}" == "RUNNING" ]]; then
      SAW_ROLLOUT="true"
    fi
  elif [[ "${CURRENT_STATUS}" == "OPERATION_IN_PROGRESS" || "${CURRENT_UPDATED_AT}" != "${PRE_PUSH_UPDATED_AT}" ]]; then
    SAW_ROLLOUT="true"
  fi

  if [[ "${SAW_ROLLOUT}" == "true" && "${CURRENT_STATUS}" == "RUNNING" ]]; then
    curl --fail --silent --show-error "${SERVICE_URL}/health" >/dev/null
    log "Deploy completed successfully for ${ENVIRONMENT}"
    exit 0
  fi

  sleep 10
done

fail "App Runner did not become healthy in time"
