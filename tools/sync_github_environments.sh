#!/usr/bin/env bash
set -euo pipefail

REPO="${GITHUB_REPOSITORY:-}"
if [[ -z "${REPO}" ]]; then
  REPO="$(gh repo view --json nameWithOwner -q '.nameWithOwner')"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

load_env_file() {
  local env_file="$1"
  if [[ -f "${env_file}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${env_file}"
    set +a
  fi
}

load_env_file "${REPO_ROOT}/.env"
load_env_file "${REPO_ROOT}/.env.local"

DEFAULT_RESEND_FROM="MediNotes <no-reply@agentairg.site>"

secret_keys=(
  AWS_ROLE_ARN
  BRAVE_API_KEY
  CLERK_JWKS_URL
  CLERK_SECRET_KEY
  DEEPSEEK_API_KEY
  DEEPSEEK_API_URL
  GEMINI_API_KEY
  GEMINI_API_URL
  GROK_API_KEY
  GROK_API_URL
  NEXT_PUBLIC_CLERK_JWT_TEMPLATE
  NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  OPENAI_API_KEY
  RESEND_API_KEY
  RESEND_FROM
  UPSTASH_REDIS_REST_TOKEN
  UPSTASH_REDIS_REST_URL
)

variable_keys=(
  AWS_ACCOUNT_ID
  DEFAULT_AWS_REGION
  RESEND_DOMAIN
)

environments=(
  "healthcare-dev:dev"
  "healthcare-prod:healthcare-saas-aws"
)

env_override_name() {
  local env_name="$1"
  local key="$2"
  local env_prefix
  env_prefix="$(printf '%s' "${env_name}" | tr '[:lower:]-' '[:upper:]_')"
  printf '%s_%s' "${env_prefix}" "${key}"
}

resolve_value() {
  local env_name="$1"
  local key="$2"
  local override_name
  override_name="$(env_override_name "${env_name}" "${key}")"

  if [[ -n "${!override_name-}" ]]; then
    printf '%s' "${!override_name}"
    return 0
  fi

  if [[ "${key}" == "RESEND_FROM" && -z "${!key-}" ]]; then
    printf '%s' "${DEFAULT_RESEND_FROM}"
    return 0
  fi

  if [[ -n "${!key-}" ]]; then
    printf '%s' "${!key}"
    return 0
  fi

  return 1
}

create_environment() {
  local env_name="$1"
  gh api \
    --method PUT \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2026-03-10" \
    "repos/${REPO}/environments/${env_name}" \
    --input - >/dev/null <<JSON
{
  "deployment_branch_policy": {
    "protected_branches": false,
    "custom_branch_policies": true
  }
}
JSON
}

sync_branch_policy() {
  local env_name="$1"
  local branch_name="$2"
  local policy_id

  while IFS= read -r policy_id; do
    [[ -z "${policy_id}" ]] && continue
    gh api \
      --method DELETE \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2026-03-10" \
      "repos/${REPO}/environments/${env_name}/deployment-branch-policies/${policy_id}" >/dev/null
  done < <(
    gh api \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2026-03-10" \
      "repos/${REPO}/environments/${env_name}/deployment-branch-policies" \
      --jq '.branch_policies[]?.id'
  )

  gh api \
    --method POST \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2026-03-10" \
    "repos/${REPO}/environments/${env_name}/deployment-branch-policies" \
    -f name="${branch_name}" \
    -f type="branch" >/dev/null
}

sync_environment_values() {
  local env_name="$1"
  local key
  local value

  for key in "${secret_keys[@]}"; do
    if value="$(resolve_value "${env_name}" "${key}")"; then
      gh secret set "${key}" --repo "${REPO}" --env "${env_name}" --body "${value}" >/dev/null
      printf 'Set secret %s in %s\n' "${key}" "${env_name}"
    else
      printf 'Skipped secret %s in %s (no local value)\n' "${key}" "${env_name}" >&2
    fi
  done

  for key in "${variable_keys[@]}"; do
    if value="$(resolve_value "${env_name}" "${key}")"; then
      gh variable set "${key}" --repo "${REPO}" --env "${env_name}" --body "${value}" >/dev/null
      printf 'Set variable %s in %s\n' "${key}" "${env_name}"
    else
      printf 'Skipped variable %s in %s (no local value)\n' "${key}" "${env_name}" >&2
    fi
  done
}

for entry in "${environments[@]}"; do
  IFS=":" read -r env_name branch_name <<< "${entry}"
  printf 'Configuring %s for branch %s\n' "${env_name}" "${branch_name}"
  create_environment "${env_name}"
  sync_branch_policy "${env_name}" "${branch_name}"
  sync_environment_values "${env_name}"
done

printf 'GitHub environment sync completed for %s\n' "${REPO}"
