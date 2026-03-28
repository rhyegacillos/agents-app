#!/bin/bash
set -e

ENVIRONMENT=${1:-dev}          # dev | test | prod
PROJECT_NAME=${2:-${APP_NAME:-digital-assistant}}

echo "🚀 Deploying ${PROJECT_NAME} to ${ENVIRONMENT}..."

# 1. Build + push Lambda container image
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"        # project root
cd "$ROOT_DIR"
echo "🐳 Building Lambda container image..."

# 2. Terraform workspace & apply
cd "$ROOT_DIR/terraform"
# Resolve var file per environment (prefers <env>.tfvars if present)
EXTRA_VARS=()
if [ -f terraform.tfvars.local ]; then
  EXTRA_VARS+=(-var-file=terraform.tfvars.local)
fi

VAR_FILE="terraform.tfvars"
if [ -f "${ENVIRONMENT}.tfvars" ]; then
  VAR_FILE="${ENVIRONMENT}.tfvars"
elif [ "$ENVIRONMENT" = "prod" ] && [ -f "prod.tfvars" ]; then
  VAR_FILE="prod.tfvars"
fi

# Keep project_name aligned with tfvars if present
TF_PROJECT_NAME="$(awk -F= '/^project_name[[:space:]]*=/{gsub(/[[:space:]\"]/, "", $2); print $2; exit}' "$VAR_FILE" 2>/dev/null || true)"
if [ -n "$TF_PROJECT_NAME" ]; then
  PROJECT_NAME="$TF_PROJECT_NAME"
fi

# terraform init -input=false
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=${AWS_REGION:-${AWS_DEFAULT_REGION:-${DEFAULT_AWS_REGION:-ap-southeast-1}}}
BACKEND_BUCKET=${TF_BACKEND_BUCKET:-${PROJECT_NAME}-terraform-state-${AWS_ACCOUNT_ID}}
BACKEND_DDB_TABLE=${TF_BACKEND_DDB_TABLE:-${PROJECT_NAME}-terraform-locks}
terraform init -reconfigure -input=false \
  -backend-config="bucket=${BACKEND_BUCKET}" \
  -backend-config="key=terraform.tfstate" \
  -backend-config="region=${AWS_REGION}" \
  -backend-config="dynamodb_table=${BACKEND_DDB_TABLE}" \
  -backend-config="encrypt=true"

if ! terraform workspace list | grep -q "$ENVIRONMENT"; then
  terraform workspace new "$ENVIRONMENT"
fi
terraform workspace select "$ENVIRONMENT"

if [ -z "${TF_VAR_runtime_secrets_arn:-}" ]; then
  chmod +x "$ROOT_DIR/scripts/runtime_secret.sh"
  TF_VAR_runtime_secrets_arn="$("$ROOT_DIR/scripts/runtime_secret.sh" sync "$ENVIRONMENT" "$PROJECT_NAME")"
  export TF_VAR_runtime_secrets_arn
fi

# Ensure ECR repo + policy exist
terraform apply -target=aws_ecr_repository.lambda -target=aws_ecr_repository_policy.lambda -var-file="$VAR_FILE" "${EXTRA_VARS[@]}" \
  -var="project_name=$PROJECT_NAME" -var="environment=$ENVIRONMENT" -auto-approve

IMAGE_TAG="${ENVIRONMENT}-latest"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
ECR_REPO="${PROJECT_NAME}-${ENVIRONMENT}-lambda"
IMAGE_URI="${ECR_REGISTRY}/${ECR_REPO}:${IMAGE_TAG}"
echo "🔧 AWS Account: ${AWS_ACCOUNT_ID} Region: ${AWS_REGION}"
echo "📦 ECR Repo: ${ECR_REPO} Tag: ${IMAGE_TAG}"

aws ecr get-login-password --region "${AWS_REGION}" | \
  docker login --username AWS --password-stdin "${ECR_REGISTRY}"

BUILD_ARGS=()
if [ "${NO_CACHE:-}" = "1" ]; then
  BUILD_ARGS+=(--no-cache)
fi

# Lambda container compatibility:
# BuildKit/buildx can emit OCI attestations (provenance/SBOM) that Lambda may reject.
# Force attestations off; if unsupported by local Docker, fallback to legacy builder.
if ! DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-1}" docker build \
  --platform linux/amd64 \
  --provenance=false \
  --sbom=false \
  "${BUILD_ARGS[@]}" \
  -t "${IMAGE_URI}" \
  "$ROOT_DIR/backend"; then
  echo "⚠️ BuildKit attestation flags unsupported or build failed. Retrying with legacy builder for Lambda compatibility..."
  DOCKER_BUILDKIT=0 docker build --platform linux/amd64 "${BUILD_ARGS[@]}" -t "${IMAGE_URI}" "$ROOT_DIR/backend"
fi
docker push "${IMAGE_URI}"

# Resolve the image digest so Lambda updates even if tag is unchanged
IMAGE_DIGEST=$(aws ecr describe-images \
  --region "${AWS_REGION}" \
  --repository-name "${ECR_REPO}" \
  --image-ids imageTag="${IMAGE_TAG}" \
  --query 'imageDetails[0].imageDigest' \
  --output text 2>/dev/null || true)
if [ -n "$IMAGE_DIGEST" ] && [ "$IMAGE_DIGEST" != "None" ]; then
  IMAGE_URI_DIGEST="${ECR_REGISTRY}/${ECR_REPO}@${IMAGE_DIGEST}"
else
  IMAGE_URI_DIGEST="${IMAGE_URI}"
fi

TF_APPLY_CMD=(terraform apply -var-file="$VAR_FILE" "${EXTRA_VARS[@]}" \
  -var="project_name=$PROJECT_NAME" -var="environment=$ENVIRONMENT" \
  -var="lambda_image_tag=$IMAGE_TAG" -auto-approve)

echo "🎯 Applying Terraform..."
"${TF_APPLY_CMD[@]}"

# Force Lambda to pull the latest image digest even when the tag is unchanged
LAMBDA_FUNCTION_NAME="$(terraform output -raw lambda_function_name 2>/dev/null || true)"
if [ -n "$LAMBDA_FUNCTION_NAME" ] && [ "$LAMBDA_FUNCTION_NAME" != "None" ]; then
  aws lambda update-function-code \
    --function-name "$LAMBDA_FUNCTION_NAME" \
    --image-uri "$IMAGE_URI_DIGEST" \
    --region "${AWS_REGION}" >/dev/null || true
fi

WORKER_FUNCTION_NAME="$(terraform output -raw worker_function_name 2>/dev/null || true)"
if [ -n "$WORKER_FUNCTION_NAME" ] && [ "$WORKER_FUNCTION_NAME" != "None" ]; then
  aws lambda update-function-code \
    --function-name "$WORKER_FUNCTION_NAME" \
    --image-uri "$IMAGE_URI_DIGEST" \
    --region "${AWS_REGION}" >/dev/null || true
fi

API_URL=$(terraform output -raw api_gateway_url)
FRONTEND_BUCKET=$(terraform output -raw s3_frontend_bucket)
CUSTOM_URL=$(terraform output -raw custom_domain_url 2>/dev/null || true)
API_CUSTOM_URL=$(terraform output -raw api_custom_domain_url 2>/dev/null || true)
FRONTEND_API_URL="$API_URL"
if [ -n "$API_CUSTOM_URL" ] && [ "$API_CUSTOM_URL" != "None" ]; then
  FRONTEND_API_URL="$API_CUSTOM_URL"
fi

# 3. Build + deploy frontend
cd ../frontend

# Create production environment file with API URL
echo "📝 Setting API URL for production..."
echo "NEXT_PUBLIC_API_URL=$FRONTEND_API_URL" > .env.production

npm install
# Prevent local dev env from overriding production API URL
ENV_LOCAL_BAK=""
if [ -f .env.local ]; then
  ENV_LOCAL_BAK=".env.local.deploy.bak"
  mv .env.local "$ENV_LOCAL_BAK"
fi

NEXT_PUBLIC_API_URL="$FRONTEND_API_URL" npm run build

if [ -n "$ENV_LOCAL_BAK" ] && [ -f "$ENV_LOCAL_BAK" ]; then
  mv "$ENV_LOCAL_BAK" .env.local
fi
# Upload HTML with no-cache to avoid stale index.html
aws s3 sync ./out "s3://$FRONTEND_BUCKET/" \
  --delete \
  --exclude "_next/static/*" \
  --cache-control "no-cache, no-store, must-revalidate"

# Upload hashed static assets with long cache
if [ -d "./out/_next/static" ]; then
  aws s3 sync ./out/_next/static "s3://$FRONTEND_BUCKET/_next/static" \
    --delete \
    --cache-control "public, max-age=31536000, immutable"
fi
cd ..

# Invalidate CloudFront so new index.html is served
CLOUDFRONT_URL=$(terraform -chdir=terraform output -raw cloudfront_url 2>/dev/null || true)
if [ -n "$CLOUDFRONT_URL" ]; then
  CF_DOMAIN="${CLOUDFRONT_URL#https://}"
  CF_DOMAIN="${CF_DOMAIN#http://}"
  DISTRIBUTION_ID=$(aws cloudfront list-distributions \
    --query "DistributionList.Items[?DomainName=='${CF_DOMAIN}'].Id | [0]" \
    --output text)
  if [ "$DISTRIBUTION_ID" != "None" ] && [ -n "$DISTRIBUTION_ID" ]; then
    aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths "/*" >/dev/null
  fi
fi

# 4. Final messages
echo -e "\n✅ Deployment complete!"
echo "🌐 CloudFront URL : $(terraform -chdir=terraform output -raw cloudfront_url)"
if [ -n "$CUSTOM_URL" ]; then
  echo "🔗 Custom domain  : $CUSTOM_URL"
fi
if [ -n "$API_CUSTOM_URL" ] && [ "$API_CUSTOM_URL" != "None" ]; then
  echo "🔗 API domain     : $API_CUSTOM_URL"
fi
echo "📡 API Gateway    : $API_URL"
