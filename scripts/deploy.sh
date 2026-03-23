#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENVIRONMENT="${1:-}"

if [[ -z "${ENVIRONMENT}" ]]; then
  echo "Usage: $0 <dev|test|prod>" >&2
  exit 1
fi

case "${ENVIRONMENT}" in
  dev|test|prod)
    ;;
  *)
    echo "Invalid environment: ${ENVIRONMENT}. Use one of: dev, test, prod." >&2
    exit 1
    ;;
esac

shift || true

exec "${SCRIPT_DIR}/deploy_terraform_local.sh" \
  --environment "${ENVIRONMENT}" \
  --tfvars-file "terraform/${ENVIRONMENT}.tfvars" \
  "$@"
