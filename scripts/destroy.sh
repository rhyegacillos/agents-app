#!/bin/bash
set -e

# Check if environment parameter is provided
if [ $# -eq 0 ]; then
    echo "❌ Error: Environment parameter is required"
    echo "Usage: $0 <environment>"
    echo "Example: $0 dev"
    echo "Available environments: dev, test, prod"
    exit 1
fi

ENVIRONMENT=$1
PROJECT_NAME=${2:-digital-assistant}

echo "🗑️ Preparing to destroy ${PROJECT_NAME}-${ENVIRONMENT} infrastructure..."

# Navigate to terraform directory
cd "$(dirname "$0")/../terraform"

# Get AWS Account ID and Region for backend configuration
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=${DEFAULT_AWS_REGION:-us-east-1}

# Initialize terraform with S3 backend
echo "🔧 Initializing Terraform with S3 backend..."
terraform init -input=false \
  -backend-config="bucket=digital-assistant-terraform-state-${AWS_ACCOUNT_ID}" \
  -backend-config="key=${ENVIRONMENT}/terraform.tfstate" \
  -backend-config="region=${AWS_REGION}" \
  -backend-config="dynamodb_table=digital-assistant-terraform-locks" \
  -backend-config="encrypt=true"

# Check if workspace exists
if ! terraform workspace list | grep -q "$ENVIRONMENT"; then
    echo "❌ Error: Workspace '$ENVIRONMENT' does not exist"
    echo "Available workspaces:"
    terraform workspace list
    exit 1
fi

# Select the workspace
terraform workspace select "$ENVIRONMENT"

EXTRA_VARS=()
if [ -f terraform.tfvars.local ]; then
    EXTRA_VARS+=(-var-file=terraform.tfvars.local)
fi

echo "🔄 Refreshing state (syncing with already-deleted resources)..."
if [ "$ENVIRONMENT" = "prod" ] && [ -f "prod.tfvars" ]; then
    terraform apply -refresh-only -var-file=prod.tfvars "${EXTRA_VARS[@]}" -var="project_name=$PROJECT_NAME" -var="environment=$ENVIRONMENT" -auto-approve
else
    terraform apply -refresh-only -var-file=terraform.tfvars "${EXTRA_VARS[@]}" -var="project_name=$PROJECT_NAME" -var="environment=$ENVIRONMENT" -auto-approve
fi

echo "📦 Emptying S3 buckets..."

# Get bucket names with account ID (matching Day 4 naming)
FRONTEND_BUCKET="${PROJECT_NAME}-${ENVIRONMENT}-frontend-${AWS_ACCOUNT_ID}"
MEMORY_BUCKET="${PROJECT_NAME}-${ENVIRONMENT}-memory-${AWS_ACCOUNT_ID}"

empty_bucket() {
    local bucket="$1"
    if ! aws s3api head-bucket --bucket "$bucket" 2>/dev/null; then
        echo "  Bucket not found or no access: $bucket"
        return
    fi

    echo "  Emptying $bucket..."
    aws s3 rm "s3://$bucket" --recursive

    # Handle versioned objects/delete markers if bucket versioning was enabled.
    local key_marker=""
    local version_marker=""
    while true; do
        local response
        if [ -n "$key_marker" ]; then
            response=$(aws s3api list-object-versions \
                --bucket "$bucket" \
                --key-marker "$key_marker" \
                --version-id-marker "$version_marker" \
                --output json)
        else
            response=$(aws s3api list-object-versions --bucket "$bucket" --output json)
        fi

        local delete_json
        delete_json=$(mktemp)
        read -r has_objects is_truncated next_key next_version <<< "$(
            printf '%s' "$response" | python3 - "$delete_json" <<'PY'
import json
import sys

data = json.load(sys.stdin)
objects = []
for v in data.get("Versions", []) or []:
    objects.append({"Key": v["Key"], "VersionId": v["VersionId"]})
for m in data.get("DeleteMarkers", []) or []:
    objects.append({"Key": m["Key"], "VersionId": m["VersionId"]})

if objects:
    with open(sys.argv[1], "w", encoding="utf-8") as fh:
        json.dump({"Objects": objects, "Quiet": True}, fh)

print(1 if objects else 0)
print(1 if data.get("IsTruncated") else 0)
print(data.get("NextKeyMarker", "") or "")
print(data.get("NextVersionIdMarker", "") or "")
PY
        )"

        if [ "$has_objects" = "1" ]; then
            aws s3api delete-objects --bucket "$bucket" --delete "file://$delete_json"
        fi
        rm -f "$delete_json"

        if [ "$is_truncated" = "1" ]; then
            key_marker="$next_key"
            version_marker="$next_version"
            continue
        fi

        break
    done
}

empty_bucket "$FRONTEND_BUCKET"
empty_bucket "$MEMORY_BUCKET"

echo "🔥 Running terraform destroy..."

# Create a dummy lambda zip if it doesn't exist (needed for destroy in GitHub Actions)
if [ ! -f "../backend/lambda-deployment.zip" ]; then
    echo "Creating dummy lambda package for destroy operation..."
    echo "dummy" | zip ../backend/lambda-deployment.zip -
fi

# Run terraform destroy with auto-approve
if [ "$ENVIRONMENT" = "prod" ] && [ -f "prod.tfvars" ]; then
    terraform destroy -var-file=prod.tfvars "${EXTRA_VARS[@]}" -var="project_name=$PROJECT_NAME" -var="environment=$ENVIRONMENT" -auto-approve
else
    terraform destroy -var-file=terraform.tfvars "${EXTRA_VARS[@]}" -var="project_name=$PROJECT_NAME" -var="environment=$ENVIRONMENT" -auto-approve
fi

echo "✅ Infrastructure for ${ENVIRONMENT} has been destroyed!"
echo ""
echo "💡 To remove the workspace completely, run:"
echo "   terraform workspace select default"
echo "   terraform workspace delete $ENVIRONMENT"
