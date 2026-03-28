#!/bin/bash
set -euo pipefail

ACTION=${1:-}
ENVIRONMENT=${2:-dev}
PROJECT_NAME=${3:-${APP_NAME:-digital-assistant}}

if [ -z "$ACTION" ]; then
  echo "Usage: $0 <sync|resolve|delete> [environment] [project_name]" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TFVARS_LOCAL="${ROOT_DIR}/terraform/terraform.tfvars.local"
SECRET_NAME="${PROJECT_NAME}/${ENVIRONMENT}/runtime"
EXPLICIT_SECRET_ID="${RUNTIME_SECRETS_ARN:-}"

secret_id() {
  if [ -n "$EXPLICIT_SECRET_ID" ]; then
    printf '%s\n' "$EXPLICIT_SECRET_ID"
  else
    printf '%s\n' "$SECRET_NAME"
  fi
}

secret_exists() {
  aws secretsmanager describe-secret --secret-id "$(secret_id)" >/dev/null 2>&1
}

resolve_secret_arn() {
  aws secretsmanager describe-secret \
    --secret-id "$(secret_id)" \
    --query 'ARN' \
    --output text 2>/dev/null || true
}

build_secret_payload() {
  local payload_file
  payload_file=$(mktemp)
  python3 - "$payload_file" "$TFVARS_LOCAL" <<'PY'
import json
import os
import pathlib
import sys

payload_path = pathlib.Path(sys.argv[1])
tfvars_path = pathlib.Path(sys.argv[2])
keys = (
    "GROK_API_KEY",
    "BRAVE_API_KEY",
    "RESEND_API_KEY",
    "UPSTASH_REDIS_REST_URL",
    "UPSTASH_REDIS_REST_TOKEN",
    "OTEL_EXPORTER_OTLP_HEADERS",
    "OTEL_EXPORTER_OTLP_LOGS_HEADERS",
)


def parse_tfvars(path: pathlib.Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_key = key.strip()
        normalized_value = value.strip()
        if normalized_value.startswith('"') and normalized_value.endswith('"'):
            normalized_value = normalized_value[1:-1]
        values[normalized_key.upper()] = normalized_value.strip()
    return values


tfvars_values = parse_tfvars(tfvars_path)
payload = {}
for key in keys:
    payload[key] = (os.getenv(key) or tfvars_values.get(key, "")).strip()

payload_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
PY
  echo "$payload_file"
}

case "$ACTION" in
  sync)
    payload_file=$(build_secret_payload)
    trap 'rm -f "$payload_file"' EXIT
    if secret_exists; then
      aws secretsmanager put-secret-value \
        --secret-id "$(secret_id)" \
        --secret-string "file://$payload_file" >/dev/null
    elif [ -n "$EXPLICIT_SECRET_ID" ]; then
      echo "Runtime secret does not exist for explicit RUNTIME_SECRETS_ARN: $EXPLICIT_SECRET_ID" >&2
      exit 1
    else
      aws secretsmanager create-secret \
        --name "$SECRET_NAME" \
        --secret-string "file://$payload_file" \
        --tags "Key=Project,Value=${PROJECT_NAME}" "Key=Environment,Value=${ENVIRONMENT}" >/dev/null
    fi
    resolve_secret_arn
    ;;
  resolve)
    resolve_secret_arn
    ;;
  delete)
    if [ -n "$EXPLICIT_SECRET_ID" ]; then
      exit 0
    fi
    if secret_exists; then
      aws secretsmanager delete-secret \
        --secret-id "$SECRET_NAME" \
        --force-delete-without-recovery >/dev/null
    fi
    ;;
  *)
    echo "Unknown action: $ACTION" >&2
    exit 1
    ;;
esac
