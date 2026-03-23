#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME=""
ENVIRONMENT=""
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-}}"
DB_HOST=""
DB_PORT="5432"
DB_NAME=""
DB_USERNAME=""
DB_MASTER_SECRET_ARN=""

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
    --db-host)
      DB_HOST="$2"
      shift 2
      ;;
    --db-port)
      DB_PORT="$2"
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
    --db-master-secret-arn)
      DB_MASTER_SECRET_ARN="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

for required in PROJECT_NAME ENVIRONMENT AWS_REGION DB_HOST DB_PORT DB_NAME DB_USERNAME DB_MASTER_SECRET_ARN OPENAI_API_KEY GEMINI_API_KEY DEEPSEEK_API_KEY GROK_API_KEY RESEND_API_KEY; do
  if [[ -z "${!required:-}" ]]; then
    echo "${required} is required." >&2
    exit 1
  fi
done

MASTER_SECRET_JSON="$(aws secretsmanager get-secret-value \
  --secret-id "${DB_MASTER_SECRET_ARN}" \
  --region "${AWS_REGION}" \
  --query SecretString \
  --output text)"

DB_PASSWORD="$(
python3 - <<'PY' "${MASTER_SECRET_JSON}"
import json
import sys
payload = json.loads(sys.argv[1])
print(payload["password"])
PY
)"

DATABASE_URL_PROD="postgresql+psycopg://${DB_USERNAME}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
SECRET_PREFIX="${PROJECT_NAME}-${ENVIRONMENT}/app"

upsert_secret() {
  local secret_name="$1"
  local secret_value="$2"

  if aws secretsmanager describe-secret --secret-id "${secret_name}" --region "${AWS_REGION}" >/dev/null 2>&1; then
    aws secretsmanager put-secret-value \
      --secret-id "${secret_name}" \
      --region "${AWS_REGION}" \
      --secret-string "${secret_value}" >/dev/null
  else
    aws secretsmanager create-secret \
      --name "${secret_name}" \
      --region "${AWS_REGION}" \
      --secret-string "${secret_value}" >/dev/null
  fi
}

upsert_secret "${SECRET_PREFIX}/DATABASE_URL_PROD" "${DATABASE_URL_PROD}"
upsert_secret "${SECRET_PREFIX}/OPENAI_API_KEY" "${OPENAI_API_KEY}"
upsert_secret "${SECRET_PREFIX}/GEMINI_API_KEY" "${GEMINI_API_KEY}"
upsert_secret "${SECRET_PREFIX}/DEEPSEEK_API_KEY" "${DEEPSEEK_API_KEY}"
upsert_secret "${SECRET_PREFIX}/GROK_API_KEY" "${GROK_API_KEY}"
upsert_secret "${SECRET_PREFIX}/RESEND_API_KEY" "${RESEND_API_KEY}"

echo "Synced app runtime secrets to AWS Secrets Manager."
