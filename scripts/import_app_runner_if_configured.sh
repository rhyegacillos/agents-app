#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

TF_DIR="terraform"
TFVARS_FILE=""
IMPORT_ID="${TF_VAR_existing_app_runner_service_arn:-}"
REPO_ROOT="$(pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --terraform-dir)
      TF_DIR="$2"
      shift 2
      ;;
    --tfvars-file)
      TFVARS_FILE="$2"
      shift 2
      ;;
    --service-arn)
      IMPORT_ID="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if terraform -chdir="${TF_DIR}" state show 'aws_apprunner_service.app[0]' >/dev/null 2>&1; then
  log "App Runner service is already in Terraform state."
  exit 0
fi

if [[ -z "${TFVARS_FILE}" ]]; then
  TFVARS_FILE="${TF_DIR}/dev.tfvars"
fi

if [[ "${TFVARS_FILE}" != /* ]]; then
  TFVARS_FILE="${REPO_ROOT}/${TFVARS_FILE}"
fi

if [[ -z "${IMPORT_ID}" && -f "${TFVARS_FILE}" ]]; then
  IMPORT_ID="$(awk -F= '/^[[:space:]]*existing_app_runner_service_arn[[:space:]]*=/{gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); gsub(/"/, "", $2); print $2}' "${TFVARS_FILE}")"
fi

if [[ -z "${IMPORT_ID}" ]]; then
  log "No existing App Runner service ARN configured; skipping import."
  exit 0
fi

log "Importing existing App Runner service into Terraform state: ${IMPORT_ID}"
terraform -chdir="${TF_DIR}" import -var="app_runner_enabled=true" 'aws_apprunner_service.app[0]' "${IMPORT_ID}"
