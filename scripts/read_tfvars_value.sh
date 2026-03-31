#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <tfvars-file> <key>" >&2
  exit 1
fi

TFVARS_FILE="$1"
KEY="$2"

if [[ ! -f "${TFVARS_FILE}" ]]; then
  echo "Terraform var-file not found: ${TFVARS_FILE}" >&2
  exit 1
fi

awk -F= -v key="${KEY}" '
  $0 ~ "^[[:space:]]*" key "[[:space:]]*=" {
    value = substr($0, index($0, "=") + 1)
    sub(/^[[:space:]]+/, "", value)
    sub(/[[:space:]]+$/, "", value)
    gsub(/"/, "", value)
    print value
    exit
  }
' "${TFVARS_FILE}"
