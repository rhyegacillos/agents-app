#!/usr/bin/env bash
set -euo pipefail

TABLE_NAME="${1:-${DYNAMODB_TABLE_NAME:-}}"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-${DEFAULT_AWS_REGION:-ap-southeast-1}}}"
ENDPOINT_URL="${DYNAMODB_ENDPOINT_URL:-}"
AWS_ARGS=(--region "${AWS_REGION}")

if [[ -n "${ENDPOINT_URL}" ]]; then
  AWS_ARGS+=(--endpoint-url "${ENDPOINT_URL}")
fi

if [[ -z "${TABLE_NAME}" ]]; then
  echo "Usage: $0 <table-name>" >&2
  echo "Or set DYNAMODB_TABLE_NAME in the environment." >&2
  exit 1
fi

if aws dynamodb describe-table --table-name "${TABLE_NAME}" "${AWS_ARGS[@]}" >/dev/null 2>&1; then
  echo "DynamoDB table ${TABLE_NAME} already exists in ${AWS_REGION}."
  exit 0
fi

aws dynamodb create-table \
  --table-name "${TABLE_NAME}" \
  "${AWS_ARGS[@]}" \
  --attribute-definitions \
    AttributeName=pk,AttributeType=S \
    AttributeName=sk,AttributeType=S \
  --key-schema \
    AttributeName=pk,KeyType=HASH \
    AttributeName=sk,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST

aws dynamodb wait table-exists \
  --table-name "${TABLE_NAME}" \
  "${AWS_ARGS[@]}"

echo "Created DynamoDB table ${TABLE_NAME} in ${AWS_REGION}."
