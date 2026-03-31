#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
READ_TFVARS_VALUE_SCRIPT="${SCRIPT_DIR}/read_tfvars_value.sh"
PROJECT_NAME="ideagen"
PROJECT_NAME_EXPLICIT="false"
ENVIRONMENT="dev"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-ap-southeast-1}}"
AWS_REGION_EXPLICIT="false"
TF_DIR="terraform"
ENV_FILE=".env"
TFVARS_FILE=""
DB_NAME="ideagen"
DB_USERNAME="ideagen"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-name)
      PROJECT_NAME="$2"
      PROJECT_NAME_EXPLICIT="true"
      shift 2
      ;;
    --environment)
      ENVIRONMENT="$2"
      shift 2
      ;;
    --region)
      AWS_REGION="$2"
      AWS_REGION_EXPLICIT="true"
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

if [[ ! -x "${READ_TFVARS_VALUE_SCRIPT}" ]]; then
  chmod +x "${READ_TFVARS_VALUE_SCRIPT}"
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

TFVARS_ENVIRONMENT="$("${READ_TFVARS_VALUE_SCRIPT}" "${TFVARS_FILE}" environment)"
TFVARS_PROJECT_NAME="$("${READ_TFVARS_VALUE_SCRIPT}" "${TFVARS_FILE}" project_name)"
TFVARS_AWS_REGION="$("${READ_TFVARS_VALUE_SCRIPT}" "${TFVARS_FILE}" aws_region)"
if [[ -n "${TFVARS_ENVIRONMENT}" && "${TFVARS_ENVIRONMENT}" != "${ENVIRONMENT}" ]]; then
  echo "Environment mismatch: script requested '${ENVIRONMENT}' but ${TFVARS_FILE} is set to '${TFVARS_ENVIRONMENT}'." >&2
  exit 1
fi

if [[ -n "${TFVARS_PROJECT_NAME}" ]]; then
  if [[ "${PROJECT_NAME_EXPLICIT}" == "true" && "${PROJECT_NAME}" != "${TFVARS_PROJECT_NAME}" ]]; then
    echo "Project mismatch: script requested '${PROJECT_NAME}' but ${TFVARS_FILE} is set to '${TFVARS_PROJECT_NAME}'." >&2
    exit 1
  fi
  PROJECT_NAME="${TFVARS_PROJECT_NAME}"
fi

if [[ -n "${TFVARS_AWS_REGION}" ]]; then
  if [[ "${AWS_REGION_EXPLICIT}" == "true" && "${AWS_REGION}" != "${TFVARS_AWS_REGION}" ]]; then
    echo "AWS region mismatch: script requested '${AWS_REGION}' but ${TFVARS_FILE} is set to '${TFVARS_AWS_REGION}'." >&2
    exit 1
  fi
  AWS_REGION="${TFVARS_AWS_REGION}"
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
