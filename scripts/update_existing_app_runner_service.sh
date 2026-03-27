#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

fail() {
  log "ERROR: $*"
  exit 1
}

wait_for_service_running() {
  local service_arn="$1"
  local attempt
  local status

  for attempt in $(seq 1 60); do
    status="$(aws apprunner describe-service --service-arn "${service_arn}" --query 'Service.Status' --output text)"
    log "Service status (${attempt}/60): ${status}"
    case "${status}" in
      RUNNING)
        return 0
        ;;
      OPERATION_IN_PROGRESS|CREATE_IN_PROGRESS)
        sleep 10
        ;;
      *)
        fail "App Runner service is not ready for update: ${status}"
        ;;
    esac
  done

  fail "Timed out waiting for App Runner service to become RUNNING"
}

TF_DIR="terraform"
TFVARS_FILE=""
SERVICE_ARN="${TF_VAR_existing_app_runner_service_arn:-}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
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
      SERVICE_ARN="$2"
      shift 2
      ;;
    --image-tag)
      IMAGE_TAG="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "${TFVARS_FILE}" ]]; then
  TFVARS_FILE="${TF_DIR}/dev.tfvars"
fi

if [[ "${TFVARS_FILE}" != /* ]]; then
  TFVARS_FILE="${REPO_ROOT}/${TFVARS_FILE}"
fi

if [[ -z "${SERVICE_ARN}" && -f "${TFVARS_FILE}" ]]; then
  SERVICE_ARN="$(awk -F= '/^[[:space:]]*existing_app_runner_service_arn[[:space:]]*=/{gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); gsub(/"/, "", $2); print $2}' "${TFVARS_FILE}")"
fi

if [[ -z "${SERVICE_ARN}" ]]; then
  fail "No existing App Runner service ARN configured."
fi

ECR_REPOSITORY_URL="$(terraform -chdir="${TF_DIR}" output -raw ecr_repository_url)"
ECR_ACCESS_ROLE_ARN="$(terraform -chdir="${TF_DIR}" output -raw app_runner_ecr_access_role_arn)"
INSTANCE_ROLE_ARN="$(terraform -chdir="${TF_DIR}" output -raw app_runner_instance_role_arn)"
VPC_CONNECTOR_ARN="$(terraform -chdir="${TF_DIR}" output -raw app_runner_vpc_connector_arn)"
AUTOSCALING_ARN="$(terraform -chdir="${TF_DIR}" output -raw app_runner_autoscaling_configuration_arn)"
RUNTIME_ENV_VARS_JSON="$(terraform -chdir="${TF_DIR}" output -json app_runner_runtime_environment_variables)"
RUNTIME_SECRET_ARNS_JSON="$(terraform -chdir="${TF_DIR}" output -json app_runtime_secret_arns)"
APP_PORT="$(terraform -chdir="${TF_DIR}" console -var-file="${TFVARS_FILE}" <<< 'var.app_port' | tr -d '"[:space:]')"
APP_CPU="$(terraform -chdir="${TF_DIR}" console -var-file="${TFVARS_FILE}" <<< 'var.app_runner_cpu' | sed 's/^"//; s/"$//')"
APP_MEMORY="$(terraform -chdir="${TF_DIR}" console -var-file="${TFVARS_FILE}" <<< 'var.app_runner_memory' | sed 's/^"//; s/"$//')"

PAYLOAD_FILE="$(mktemp)"
python3 - <<'PY' "${PAYLOAD_FILE}" "${SERVICE_ARN}" "${ECR_REPOSITORY_URL}" "${IMAGE_TAG}" "${ECR_ACCESS_ROLE_ARN}" "${INSTANCE_ROLE_ARN}" "${VPC_CONNECTOR_ARN}" "${AUTOSCALING_ARN}" "${APP_PORT}" "${APP_CPU}" "${APP_MEMORY}" "${RUNTIME_ENV_VARS_JSON}" "${RUNTIME_SECRET_ARNS_JSON}"
import json
import sys

payload_path = sys.argv[1]
service_arn = sys.argv[2]
ecr_repository_url = sys.argv[3]
image_tag = sys.argv[4]
ecr_access_role_arn = sys.argv[5]
instance_role_arn = sys.argv[6]
vpc_connector_arn = sys.argv[7]
autoscaling_arn = sys.argv[8]
app_port = sys.argv[9]
app_cpu = sys.argv[10]
app_memory = sys.argv[11]
runtime_env_vars = json.loads(sys.argv[12])
runtime_secret_arns = json.loads(sys.argv[13])

payload = {
    "ServiceArn": service_arn,
    "SourceConfiguration": {
        "AutoDeploymentsEnabled": False,
        "AuthenticationConfiguration": {
            "AccessRoleArn": ecr_access_role_arn,
        },
        "ImageRepository": {
            "ImageRepositoryType": "ECR",
            "ImageIdentifier": f"{ecr_repository_url}:{image_tag}",
            "ImageConfiguration": {
                "Port": app_port,
                "RuntimeEnvironmentVariables": runtime_env_vars,
                "RuntimeEnvironmentSecrets": runtime_secret_arns,
            },
        },
    },
    "InstanceConfiguration": {
        "Cpu": app_cpu,
        "Memory": app_memory,
        "InstanceRoleArn": instance_role_arn,
    },
    "AutoScalingConfigurationArn": autoscaling_arn,
    "HealthCheckConfiguration": {
        "Protocol": "HTTP",
        "Path": "/health",
        "Interval": 10,
        "Timeout": 5,
        "HealthyThreshold": 1,
        "UnhealthyThreshold": 5,
    },
    "NetworkConfiguration": {
        "IngressConfiguration": {
            "IsPubliclyAccessible": True,
        },
        "EgressConfiguration": {
            "EgressType": "VPC",
            "VpcConnectorArn": vpc_connector_arn,
        },
    },
}

with open(payload_path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle)
PY

log "Waiting for existing App Runner operations to finish"
wait_for_service_running "${SERVICE_ARN}"

log "Updating existing App Runner service ${SERVICE_ARN}"
aws apprunner update-service --cli-input-json "file://${PAYLOAD_FILE}" >/dev/null
rm -f "${PAYLOAD_FILE}"

SERVICE_URL="$(aws apprunner describe-service --service-arn "${SERVICE_ARN}" --query 'Service.ServiceUrl' --output text)"
wait_for_service_running "${SERVICE_ARN}"
log "Waiting for App Runner health check at https://${SERVICE_URL}/health"
for attempt in $(seq 1 60); do
  if curl -fsS "https://${SERVICE_URL}/health" >/dev/null; then
    log "Deployment healthy: https://${SERVICE_URL}/health"
    exit 0
  fi
  log "Health check not ready yet (${attempt}/60), retrying in 10s"
  sleep 10
done

fail "App Runner health check did not pass in time: https://${SERVICE_URL}/health"
