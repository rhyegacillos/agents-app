#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="ideagen"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-}}"
GITHUB_OUTPUT_MODE="false"

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
    --github-output)
      GITHUB_OUTPUT_MODE="true"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "${AWS_REGION}" ]]; then
  echo "AWS region is required. Pass --region or set AWS_REGION/AWS_DEFAULT_REGION." >&2
  exit 1
fi

ACCOUNT_ID="$(aws sts get-caller-identity --query 'Account' --output text)"
BUCKET_NAME="${PROJECT_NAME}-terraform-state-${ACCOUNT_ID}-${AWS_REGION}"
LOCK_TABLE_NAME="${PROJECT_NAME}-terraform-locks"

if ! aws s3api head-bucket --bucket "${BUCKET_NAME}" >/dev/null 2>&1; then
  if [[ "${AWS_REGION}" == "us-east-1" ]]; then
    aws s3api create-bucket --bucket "${BUCKET_NAME}" >/dev/null
  else
    aws s3api create-bucket \
      --bucket "${BUCKET_NAME}" \
      --region "${AWS_REGION}" \
      --create-bucket-configuration "LocationConstraint=${AWS_REGION}" >/dev/null
  fi
fi

aws s3api put-bucket-versioning \
  --bucket "${BUCKET_NAME}" \
  --versioning-configuration Status=Enabled >/dev/null

aws s3api put-bucket-encryption \
  --bucket "${BUCKET_NAME}" \
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
  --bucket "${BUCKET_NAME}" \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true >/dev/null

if ! aws dynamodb describe-table --table-name "${LOCK_TABLE_NAME}" --region "${AWS_REGION}" >/dev/null 2>&1; then
  aws dynamodb create-table \
    --table-name "${LOCK_TABLE_NAME}" \
    --region "${AWS_REGION}" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST >/dev/null

  aws dynamodb wait table-exists \
    --table-name "${LOCK_TABLE_NAME}" \
    --region "${AWS_REGION}"
fi

if [[ "${GITHUB_OUTPUT_MODE}" == "true" ]]; then
  if [[ -z "${GITHUB_OUTPUT:-}" ]]; then
    echo "GITHUB_OUTPUT is not set." >&2
    exit 1
  fi
  {
    echo "bucket=${BUCKET_NAME}"
    echo "lock_table=${LOCK_TABLE_NAME}"
    echo "aws_region=${AWS_REGION}"
  } >> "${GITHUB_OUTPUT}"
else
  echo "TF_BACKEND_BUCKET=${BUCKET_NAME}"
  echo "TF_BACKEND_DDB_TABLE=${LOCK_TABLE_NAME}"
  echo "AWS_REGION=${AWS_REGION}"
fi
