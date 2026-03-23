#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_NAME="ideagen"
ENVIRONMENT="dev"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-ap-southeast-1}}"
TF_DIR="terraform"
ENV_FILE=".env"
TFVARS_FILE=""
DB_NAME="ideagen"
DB_USERNAME="ideagen"

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
    --db-name)
      DB_NAME="$2"
      shift 2
      ;;
    --db-username)
      DB_USERNAME="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Env file not found: ${ENV_FILE}" >&2
  exit 1
fi

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
  echo "Terraform var-file not found: ${TFVARS_FILE}" >&2
  exit 1
fi

TFVARS_ENVIRONMENT="$(awk -F= '/^[[:space:]]*environment[[:space:]]*=/{gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); gsub(/"/, "", $2); print $2; exit}' "${TFVARS_FILE}")"
if [[ -n "${TFVARS_ENVIRONMENT}" && "${TFVARS_ENVIRONMENT}" != "${ENVIRONMENT}" ]]; then
  echo "Environment mismatch: script requested '${ENVIRONMENT}' but ${TFVARS_FILE} is set to '${TFVARS_ENVIRONMENT}'." >&2
  exit 1
fi

export AWS_REGION
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-${AWS_REGION}}"

terraform -chdir="${TF_DIR}" workspace select "${ENVIRONMENT}" >/dev/null 2>&1 || true

DB_HOST="$(terraform -chdir="${TF_DIR}" output -raw rds_endpoint)"
DB_PORT="$(terraform -chdir="${TF_DIR}" output -raw rds_port)"
DB_MASTER_SECRET_ARN="$(terraform -chdir="${TF_DIR}" output -raw rds_master_user_secret_arn)"

"${SCRIPT_DIR}/sync_app_secrets.sh" \
  --project-name "${PROJECT_NAME}" \
  --environment "${ENVIRONMENT}" \
  --region "${AWS_REGION}" \
  --db-host "${DB_HOST}" \
  --db-port "${DB_PORT}" \
  --db-name "${DB_NAME}" \
  --db-username "${DB_USERNAME}" \
  --db-master-secret-arn "${DB_MASTER_SECRET_ARN}"
