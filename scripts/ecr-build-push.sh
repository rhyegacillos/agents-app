#!/usr/bin/env bash
set -euo pipefail

# Builds and pushes the app image to ECR.
# Intended to be called by scripts/terraform-deploy.sh, but can be run standalone.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

AWS_REGION="${AWS_REGION:-}"
ECR_REPO="${ECR_REPO:-}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
DOCKER_PLATFORM="${DOCKER_PLATFORM:-linux/amd64}"

usage() {
  cat <<'EOF'
Usage:
  AWS_REGION=ap-southeast-1 ECR_REPO=autonomous-trader IMAGE_TAG=latest ./scripts/ecr-build-push.sh

Optional env:
  DOCKER_PLATFORM=linux/amd64   (default)
EOF
}

if [[ -z "${AWS_REGION}" || -z "${ECR_REPO}" ]]; then
  usage >&2
  echo "ERROR: AWS_REGION and ECR_REPO are required." >&2
  exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "ERROR: aws CLI is required to push to ECR." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is required to build/push the image." >&2
  exit 1
fi

account_id="$(aws sts get-caller-identity --query Account --output text 2>/dev/null || true)"
if [[ -z "${account_id}" || "${account_id}" == "None" ]]; then
  echo "ERROR: Could not determine AWS account id (check AWS credentials)." >&2
  exit 1
fi

image_uri="${account_id}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}"
registry="${account_id}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Ensure repository exists (portable / zero manual console steps).
if ! aws ecr describe-repositories --repository-names "${ECR_REPO}" --region "${AWS_REGION}" >/dev/null 2>&1; then
  echo "ECR repo ${ECR_REPO} not found; creating..."
  aws ecr create-repository --repository-name "${ECR_REPO}" --region "${AWS_REGION}" >/dev/null
fi

echo "Logging into ECR registry ${registry}..."
aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${registry}" >/dev/null

echo "Building and pushing ${image_uri} (platform: ${DOCKER_PLATFORM})..."
cd "${REPO_ROOT}"

# Prefer buildx for cross-platform builds. Fall back to normal build + push.
if docker buildx version >/dev/null 2>&1; then
  docker buildx build --platform "${DOCKER_PLATFORM}" -t "${image_uri}" --push .
else
  docker build -t "${image_uri}" .
  docker push "${image_uri}"
fi

echo "Pushed: ${image_uri}"

