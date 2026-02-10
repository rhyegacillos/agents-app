#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="${SCRIPT_DIR}/../terraform"

if [[ ! -d "${TF_DIR}" ]]; then
  echo "Terraform directory not found at ${TF_DIR}" >&2
  exit 1
fi

if [[ -f "${TF_DIR}/terraform.tfvars.local" ]]; then
  cp "${TF_DIR}/terraform.tfvars.local" "${TF_DIR}/terraform.tfvars"
fi

if [[ ! -f "${TF_DIR}/terraform.tfvars" ]]; then
  if [[ -f "${TF_DIR}/terraform.tfvars.example" ]]; then
    echo "Missing terraform/terraform.tfvars. Copy terraform/terraform.tfvars.example to terraform.tfvars.local and fill values." >&2
  else
    echo "Missing terraform/terraform.tfvars." >&2
  fi
  exit 1
fi

cd "${TF_DIR}"
terraform init
terraform destroy -auto-approve
