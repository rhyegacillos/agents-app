#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

fail() {
  log "ERROR: $*"
  exit 1
}

get_service_status() {
  local service_arn="$1"
  aws apprunner describe-service \
    --service-arn "${service_arn}" \
    --region "${AWS_REGION}" \
    --query 'Service.Status' \
    --output text
}

wait_for_service_running() {
  local service_arn="$1"
  local max_attempts="${2:-60}"
  local status=""

  for attempt in $(seq 1 "${max_attempts}"); do
    status="$(get_service_status "${service_arn}")"
    log "App Runner status (${attempt}/${max_attempts}): ${status}"
    if [[ "${status}" == "RUNNING" ]]; then
      return 0
    fi
    sleep 10
  done

  fail "App Runner did not reach RUNNING state in time"
}

has_managed_apprunner() {
  terraform -chdir="${TF_DIR}" state show 'aws_apprunner_service.app[0]' >/dev/null 2>&1
}

bootstrap_without_apprunner() {
  log "First deploy detected. Bootstrapping prerequisite infrastructure without App Runner"
  terraform -chdir="${TF_DIR}" apply -auto-approve -var-file="${TFVARS_FILE}" \
    "${TERRAFORM_OVERRIDE_ARGS[@]}" \
    -target=aws_vpc.main \
    -target=aws_internet_gateway.main \
    -target=aws_subnet.public \
    -target=aws_subnet.private_app \
    -target=aws_subnet.private_db \
    -target=aws_eip.nat \
    -target=aws_nat_gateway.main \
    -target=aws_route_table.public \
    -target=aws_route.public_internet \
    -target=aws_route_table_association.public \
    -target=aws_route_table.private \
    -target=aws_route.private_nat \
    -target=aws_route_table_association.private_app \
    -target=aws_route_table_association.private_db \
    -target=aws_security_group.app_runner \
    -target=aws_security_group.db \
    -target=aws_db_subnet_group.postgres \
    -target=aws_db_instance.postgres \
    -target=aws_ecr_repository.app \
    -target=aws_ecr_lifecycle_policy.app \
    -target=aws_iam_role.apprunner_ecr_access \
    -target=aws_iam_role_policy_attachment.apprunner_ecr_access \
    -target=aws_iam_role.apprunner_instance \
    -target=aws_iam_role_policy.apprunner_instance_secrets \
    -target=aws_apprunner_vpc_connector.main \
    -target=aws_apprunner_auto_scaling_configuration_version.main \
    -target=aws_secretsmanager_secret.database_url_prod \
    -target=aws_secretsmanager_secret.openai_api_key \
    -target=aws_secretsmanager_secret.gemini_api_key \
    -target=aws_secretsmanager_secret.deepseek_api_key \
    -target=aws_secretsmanager_secret.grok_api_key \
    -target=aws_secretsmanager_secret.resend_api_key
}

export_matching_tf_vars() {
  local variables_file="$1"
  local matched=()
  local var_name=""
  local env_name=""

  while IFS= read -r var_name; do
    env_name="$(printf '%s' "${var_name}" | tr '[:lower:]' '[:upper:]')"
    if [[ -n "${!env_name:-}" ]]; then
      export "TF_VAR_${var_name}=${!env_name}"
      matched+=("${var_name}")
    fi
  done < <(awk -F'"' '/^variable "/ {print $2}' "${variables_file}")

  if [[ ${#matched[@]} -gt 0 ]]; then
    log "Terraform env overrides from .env: ${matched[*]}"
  fi
}

build_terraform_override_args() {
  TERRAFORM_OVERRIDE_ARGS=()

  local mappings=(
    "allowed_hosts:ALLOWED_HOSTS"
    "next_public_clerk_publishable_key:NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"
    "clerk_jwks_url:CLERK_JWKS_URL"
    "gemini_api_url:GEMINI_API_URL"
    "deepseek_api_url:DEEPSEEK_API_URL"
    "grok_api_url:GROK_API_URL"
    "email_from:EMAIL_FROM"
  )

  local mapping=""
  local tf_name=""
  local env_name=""
  local matched=()

  for mapping in "${mappings[@]}"; do
    tf_name="${mapping%%:*}"
    env_name="${mapping##*:}"
    if [[ -n "${!env_name:-}" ]]; then
      TERRAFORM_OVERRIDE_ARGS+=("-var=${tf_name}=${!env_name}")
      matched+=("${tf_name}")
    fi
  done

  if [[ ${#matched[@]} -gt 0 ]]; then
    log "Terraform explicit overrides: ${matched[*]}"
  fi
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_NAME="ideagen"
ENVIRONMENT="dev"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-ap-southeast-1}}"
TF_DIR="terraform"
ENV_FILE=".env"
TFVARS_FILE=""
SKIP_APP_RUNNER="false"
IMAGE_TAG="${IMAGE_TAG:-latest}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-name)
      PROJECT_NAME="$2"
      shift 2
      ;;
    --environment)
      ENVIRONMENT="$2"
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
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --tfvars-file)
      TFVARS_FILE="$2"
      shift 2
      ;;
    --image-tag)
      IMAGE_TAG="$2"
      shift 2
      ;;
    --skip-app-runner)
      SKIP_APP_RUNNER="true"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -f "${ENV_FILE}" ]]; then
  fail "Env file not found: ${ENV_FILE}"
fi

log "Loading environment from ${ENV_FILE}"
set -a
source "${ENV_FILE}"
set +a

if [[ -z "${TFVARS_FILE}" ]]; then
  TFVARS_FILE="${TF_DIR}/${ENVIRONMENT}.tfvars"
fi

if [[ "${TFVARS_FILE}" != /* ]]; then
  TFVARS_FILE="${REPO_ROOT}/${TFVARS_FILE}"
fi

if [[ ! -f "${TFVARS_FILE}" ]]; then
  fail "Terraform var-file not found: ${TFVARS_FILE}"
fi

TFVARS_ENVIRONMENT="$(awk -F= '/^[[:space:]]*environment[[:space:]]*=/{gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); gsub(/"/, "", $2); print $2; exit}' "${TFVARS_FILE}")"
if [[ -n "${TFVARS_ENVIRONMENT}" && "${TFVARS_ENVIRONMENT}" != "${ENVIRONMENT}" ]]; then
  fail "Environment mismatch: script requested '${ENVIRONMENT}' but ${TFVARS_FILE} is set to '${TFVARS_ENVIRONMENT}'."
fi

for required in NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY OPENAI_API_KEY GEMINI_API_KEY DEEPSEEK_API_KEY GROK_API_KEY RESEND_API_KEY; do
  if [[ -z "${!required:-}" ]]; then
    fail "${required} is required in ${ENV_FILE}."
  fi
done

export AWS_REGION
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-${AWS_REGION}}"

export_matching_tf_vars "${REPO_ROOT}/${TF_DIR}/variables.tf"
build_terraform_override_args

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

if has_managed_apprunner; then
  log "Managed App Runner already exists in Terraform state. Skipping bootstrap apply"
else
  bootstrap_without_apprunner
fi

ECR_REPOSITORY_URL="$(terraform -chdir="${TF_DIR}" output -raw ecr_repository_url)"
log "Resolved ECR repository ${ECR_REPOSITORY_URL}"

log "Syncing runtime secrets to AWS Secrets Manager"
"${SCRIPT_DIR}/sync_app_secrets_local.sh" \
  --project-name "${PROJECT_NAME}" \
  --environment "${ENVIRONMENT}" \
  --region "${AWS_REGION}" \
  --terraform-dir "${TF_DIR}" \
  --env-file "${ENV_FILE}" \
  --tfvars-file "${TFVARS_FILE}"

REGISTRY_HOST="${ECR_REPOSITORY_URL%%/*}"
log "Logging in to ECR registry ${REGISTRY_HOST}"
aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${REGISTRY_HOST}"

log "Building Docker image ${ECR_REPOSITORY_URL}:${IMAGE_TAG}"
docker build \
  --build-arg "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=${NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY}" \
  -t "${ECR_REPOSITORY_URL}:${IMAGE_TAG}" \
  .

log "Pushing Docker image ${ECR_REPOSITORY_URL}:${IMAGE_TAG}"
docker push "${ECR_REPOSITORY_URL}:${IMAGE_TAG}"

if [[ "${IMAGE_TAG}" != "latest" ]]; then
  log "Tagging ${IMAGE_TAG} as latest"
  docker tag "${ECR_REPOSITORY_URL}:${IMAGE_TAG}" "${ECR_REPOSITORY_URL}:latest"
  log "Pushing Docker image ${ECR_REPOSITORY_URL}:latest"
  docker push "${ECR_REPOSITORY_URL}:latest"
fi

if [[ "${SKIP_APP_RUNNER}" == "true" ]]; then
  log "Infrastructure, secrets, and image push completed. App Runner apply was skipped."
  log "Run again without --skip-app-runner to create or update App Runner."
else
  EXISTING_SERVICE_ARN="$(awk -F= '/^[[:space:]]*existing_app_runner_service_arn[[:space:]]*=/{gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); gsub(/"/, "", $2); print $2; exit}' "${TFVARS_FILE}" 2>/dev/null || true)"

  if [[ -n "${TF_VAR_existing_app_runner_service_arn:-}" || -n "${EXISTING_SERVICE_ARN}" ]]; then
    log "Updating configured existing App Runner service via AWS CLI"
    "${SCRIPT_DIR}/update_existing_app_runner_service.sh" --terraform-dir "${TF_DIR}" --tfvars-file "${TFVARS_FILE}" --image-tag "${IMAGE_TAG}"
  else
    log "Applying Terraform with App Runner enabled"
    terraform -chdir="${TF_DIR}" apply -auto-approve -var-file="${TFVARS_FILE}" \
      "${TERRAFORM_OVERRIDE_ARGS[@]}" \
      -var="app_runner_enabled=true" \
      -var="ecr_image_tag=${IMAGE_TAG}"

    SERVICE_ARN="$(terraform -chdir="${TF_DIR}" output -raw app_runner_service_arn)"
    SERVICE_URL="$(terraform -chdir="${TF_DIR}" output -raw app_runner_service_url)"
    CUSTOM_DOMAIN="$(terraform -chdir="${TF_DIR}" console -var-file="${TFVARS_FILE}" <<< 'trimspace(var.app_runner_custom_domain)' | sed 's/^"//; s/"$//')"
	    CUSTOM_DOMAIN_DNS_TARGET="$(terraform -chdir="${TF_DIR}" output -raw app_runner_custom_domain_dns_target 2>/dev/null || true)"
	    CUSTOM_DOMAIN_STATUS="$(terraform -chdir="${TF_DIR}" output -raw app_runner_custom_domain_status 2>/dev/null || true)"
	    CUSTOM_DOMAIN_VALIDATION_RECORDS="$(terraform -chdir="${TF_DIR}" output -json app_runner_custom_domain_validation_records 2>/dev/null || echo '[]')"

	    CURRENT_STATUS="$(get_service_status "${SERVICE_ARN}")"
	    if [[ "${CURRENT_STATUS}" == "RUNNING" ]]; then
	      log "Triggering App Runner deployment"
	      aws apprunner start-deployment --service-arn "${SERVICE_ARN}" >/dev/null
	      wait_for_service_running "${SERVICE_ARN}"
	    else
	      log "Terraform already triggered an App Runner rollout. Waiting for RUNNING instead of starting another deployment"
	      wait_for_service_running "${SERVICE_ARN}"
	    fi

	    log "App Runner default URL: ${SERVICE_URL}"
	    if [[ -n "${CUSTOM_DOMAIN}" ]]; then
	      log "App Runner custom domain: https://${CUSTOM_DOMAIN}"
      if [[ -n "${CUSTOM_DOMAIN_DNS_TARGET}" ]]; then
        log "Custom domain DNS target: ${CUSTOM_DOMAIN_DNS_TARGET}"
      fi
      if [[ "${CUSTOM_DOMAIN_VALIDATION_RECORDS}" != "[]" ]]; then
        log "Custom domain validation records: ${CUSTOM_DOMAIN_VALIDATION_RECORDS}"
      fi
      if [[ -n "${CUSTOM_DOMAIN_STATUS}" ]]; then
        log "Custom domain status: ${CUSTOM_DOMAIN_STATUS}"
      fi
    fi

    log "Waiting for App Runner health check at ${SERVICE_URL}/health"
    for attempt in $(seq 1 60); do
      if curl -fsS "${SERVICE_URL}/health" >/dev/null; then
        log "Deployment healthy: ${SERVICE_URL}/health"
        exit 0
      fi
      log "Health check not ready yet (${attempt}/60), retrying in 10s"
      sleep 10
    done

    fail "App Runner health check did not pass in time: ${SERVICE_URL}/health"
  fi
fi
