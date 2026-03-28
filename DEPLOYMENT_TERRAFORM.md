# Terraform Deployment Guide

This document describes the current Terraform and script-based deployment
model for this repo. It reflects the repo as it exists now, including:

- Bedrock as the deployment default
- Terraform-managed infrastructure with S3 backend and DynamoDB locking
- runtime secrets stored in AWS Secrets Manager
- `scripts/deploy.sh` and `scripts/destroy.sh` as the local and CI entrypoints
- GitHub Actions passing only `runtime_secrets_arn` into Terraform instead of
  raw runtime API keys

-------------------------------------------------------------------------------

## 0) Quick start

### 0.1 Local deploy

```bash
# Confirm identity
aws sts get-caller-identity

# Deploy dev
./scripts/deploy.sh dev

# Deploy prod
./scripts/deploy.sh prod
```

### 0.2 Local destroy

```bash
./scripts/destroy.sh dev
./scripts/destroy.sh prod
```

-------------------------------------------------------------------------------

## 1) What Terraform manages

Terraform provisions the AWS resources for this application, including:

- ECR repository for the Lambda image
- API Lambda
- async worker Lambda
- S3 bucket for frontend hosting
- S3 bucket for memory and artifact persistence
- CloudFront distribution
- API Gateway REST API
- optional custom domains and Route53 records
- IAM roles and policies for Lambda
- Terraform remote state backend usage

The Terraform entrypoint in practice is not raw `terraform apply` from a human.
The normal operational entrypoints are:

- [deploy.sh](/home/repos/twin/scripts/deploy.sh)
- [destroy.sh](/home/repos/twin/scripts/destroy.sh)

-------------------------------------------------------------------------------

## 2) Current deployment model

### 2.1 Bedrock-first deployment

The current deployment default is Bedrock.

Evidence in repo:

- [terraform/terraform.tfvars](/home/repos/twin/terraform/terraform.tfvars)
  sets `ai_provider = "bedrock"`
- [terraform/prod.tfvars](/home/repos/twin/terraform/prod.tfvars)
  sets `ai_provider = "bedrock"`
- [ci.yml](/home/repos/twin/.github/workflows/ci.yml)
  exports `TF_VAR_ai_provider: bedrock`

This does not mean Grok code paths are deleted. It means the deployed default
for this stack is Bedrock-first.

### 2.2 Split domain model in prod

When `use_custom_domain = true`, the stack uses split frontend/API domains:

- website: `https://<project_name>.<root_domain>`
- API: `https://<api_subdomain>.<root_domain>`

Current prod values in [prod.tfvars](/home/repos/twin/terraform/prod.tfvars):

- `project_name = "digital-assistant"`
- `root_domain = "agentairg.site"`
- `api_subdomain = "api"`

That produces:

- website: `https://digital-assistant.agentairg.site`
- API: `https://api.agentairg.site`

-------------------------------------------------------------------------------

## 3) Environment model

Terraform environments are isolated by workspace:

- `dev`
- `test`
- `prod`

The scripts select the workspace that matches the environment argument.

Example:

```bash
./scripts/deploy.sh prod
```

This causes:

1. Terraform init against the configured backend
2. workspace select or create for `prod`
3. apply against the `prod` state

### 3.1 Var file selection

[deploy.sh](/home/repos/twin/scripts/deploy.sh) resolves the var file in this
order:

1. `terraform/<environment>.tfvars` if it exists
2. `terraform/prod.tfvars` for `prod`
3. otherwise `terraform/terraform.tfvars`

It also optionally includes:

- `terraform/terraform.tfvars.local`

if that local file exists.

-------------------------------------------------------------------------------

## 4) State backend and locking

Terraform uses:

- S3 for remote state
- DynamoDB for state locking

The scripts resolve the backend names like this:

- bucket: `${PROJECT_NAME}-terraform-state-${AWS_ACCOUNT_ID}`
- table: `${PROJECT_NAME}-terraform-locks`

unless overridden by:

- `TF_BACKEND_BUCKET`
- `TF_BACKEND_DDB_TABLE`

This logic is shared by:

- [deploy.sh](/home/repos/twin/scripts/deploy.sh)
- [destroy.sh](/home/repos/twin/scripts/destroy.sh)

### 4.1 Why locking matters

The deploy path uses real Terraform apply, not a wrapper service. Without
DynamoDB locking, concurrent runs could corrupt shared state or partially
interleave resource changes.

-------------------------------------------------------------------------------

## 5) Runtime secret model

This is the most important deployment change relative to the older docs.

### 5.1 What changed

The stack no longer treats runtime API keys as primary Terraform inputs.

Older shape:

- `grok_api_key`
- `brave_api_key`
- `resend_api_key`

were effectively part of the Terraform-managed deployment shape.

Current shape:

- runtime secrets are stored in AWS Secrets Manager
- Terraform receives only `runtime_secrets_arn`
- Lambda receives only `APP_RUNTIME_SECRETS_ARN`
- the application loads the actual secret values at runtime

### 5.2 What Terraform still knows

Terraform still has these variables declared in
[variables.tf](/home/repos/twin/terraform/variables.tf):

- `grok_api_key`
- `brave_api_key`
- `resend_api_key`

But they are now optional with empty defaults and are no longer required for
deploy to proceed.

That change was made specifically to stop Terraform from blocking deploys on
secret values it no longer consumes operationally.

### 5.3 What Terraform uses now

The infrastructure-relevant secret input is:

```hcl
variable "runtime_secrets_arn" {
  description = "Secrets Manager ARN that holds runtime-only secret values"
  type        = string
  default     = ""
}
```

Terraform then injects:

- `APP_RUNTIME_SECRETS_ARN`

into the Lambda environment and grants Lambda:

- `secretsmanager:GetSecretValue`

on that specific secret ARN.

### 5.4 Runtime secret naming

The helper script [runtime_secret.sh](/home/repos/twin/scripts/runtime_secret.sh)
uses this logical secret name when no explicit ARN is provided:

```text
<project_name>/<environment>/runtime
```

Examples:

- `digital-assistant/dev/runtime`
- `digital-assistant/prod/runtime`

### 5.5 What `runtime_secret.sh` actually does

Supported actions:

- `sync`
- `resolve`
- `delete`

Behavior:

- `sync`
  - builds a JSON payload from environment variables or
    `terraform/terraform.tfvars.local`
  - if `RUNTIME_SECRETS_ARN` is set, writes directly to that secret with
    `PutSecretValue`
  - otherwise creates or updates `<project>/<env>/runtime`
- `resolve`
  - returns the explicit ARN if one was provided
  - otherwise describes the named secret and returns its ARN
- `delete`
  - deletes only named auto-managed secrets
  - exits without deleting anything if `RUNTIME_SECRETS_ARN` was explicitly set

That last point is important: destroys do not delete precreated shared runtime
secrets.

-------------------------------------------------------------------------------

## 6) What `deploy.sh` does now

[deploy.sh](/home/repos/twin/scripts/deploy.sh) is the canonical local/CI
deployment entrypoint.

Sequence:

1. normalize environment variables:
   - unset empty `TF_VAR_bedrock_model_id`
   - unset empty `TF_VAR_async_chat_enabled`
   - map `RUNTIME_SECRETS_ARN` into `TF_VAR_runtime_secrets_arn` if needed
2. resolve the effective Terraform var file
3. read the project name from the var file if present
4. initialize Terraform backend
5. select or create the workspace
6. ensure `TF_VAR_runtime_secrets_arn` is populated:
   - use existing env value if provided
   - otherwise call `runtime_secret.sh sync`
7. apply Terraform for the ECR repository first
8. build and push the backend Lambda image
9. resolve the pushed image digest
10. run the main Terraform apply
11. force Lambda image update by digest
12. read Terraform outputs
13. build the frontend using the selected API URL
14. upload frontend files to S3
15. invalidate CloudFront

### 6.1 Frontend API URL behavior

The script prefers:

- `api_custom_domain_url`

and falls back to:

- `api_gateway_url`

for `NEXT_PUBLIC_API_URL`.

That keeps prod frontend pointing at the custom API domain when one exists.

### 6.2 Lambda image behavior

The script pushes a tag like:

- `dev-latest`
- `prod-latest`

Then it resolves the image digest and calls `aws lambda update-function-code`
with the digest URI to ensure Lambda refreshes even if the mutable tag name
does not change.

-------------------------------------------------------------------------------

## 7) What `destroy.sh` does now

[destroy.sh](/home/repos/twin/scripts/destroy.sh) is the canonical destroy path.

Sequence:

1. validate environment argument
2. initialize the Terraform backend
3. select the matching workspace
4. resolve `TF_VAR_runtime_secrets_arn` if needed
5. optionally include `terraform.tfvars.local`
6. run `terraform apply -refresh-only`
7. empty frontend and memory S3 buckets
8. run `terraform destroy`
9. call `runtime_secret.sh delete`

### 7.1 Important destroy behavior

If the runtime secret came from an explicit ARN, `runtime_secret.sh delete`
does nothing. That is intentional. Shared or precreated secrets are not removed
as part of environment destroy.

-------------------------------------------------------------------------------

## 8) Current Terraform files that matter

### 8.1 Base variables

Key files:

- [terraform/variables.tf](/home/repos/twin/terraform/variables.tf)
- [terraform/terraform.tfvars](/home/repos/twin/terraform/terraform.tfvars)
- [terraform/prod.tfvars](/home/repos/twin/terraform/prod.tfvars)

Important current base values:

- `default_aws_region = "ap-southeast-1"`
- `ai_provider = "bedrock"`
- `async_chat_enabled = true` in both current shipped var files

### 8.2 Prod-specific values

Current notable prod overrides in
[prod.tfvars](/home/repos/twin/terraform/prod.tfvars):

- `environment = "prod"`
- `bedrock_model_id = "arn:aws:bedrock:ap-southeast-1:348375262167:inference-profile/apac.amazon.nova-pro-v1:0"`
- `lambda_image_tag = "prod-latest"`
- `use_custom_domain = true`
- `root_domain = "agentairg.site"`
- `api_subdomain = "api"`
- `api_throttle_rate_limit = 20`

### 8.3 Local-only values

`terraform/terraform.tfvars.local` is still supported for local operations, but
it must remain uncommitted.

It is used for:

- optional local overrides
- bootstrapping runtime secret payload values if you run
  `runtime_secret.sh sync` locally without exporting env vars

Because it can contain plaintext credentials, it is operationally sensitive and
should be treated as a local secret file, not normal config.

-------------------------------------------------------------------------------

## 9) Local deployment patterns

### 9.1 Preferred local pattern

Use a precreated environment-specific runtime secret ARN and export it before
deploy:

```bash
export RUNTIME_SECRETS_ARN='arn:aws:secretsmanager:ap-southeast-1:<ACCOUNT_ID>:secret:digital-assistant/prod/runtime-xxxxx'
./scripts/deploy.sh prod
```

This matches the GitHub Actions model and avoids accidental secret creation
drift.

### 9.2 Fallback local pattern

If `RUNTIME_SECRETS_ARN` is not set, `deploy.sh` will call:

```bash
./scripts/runtime_secret.sh sync <env> <project>
```

That can create or update `<project>/<env>/runtime` automatically.

This is convenient, but it makes your local machine responsible for secret
creation policy, so it is less controlled than the precreated-secret path.

-------------------------------------------------------------------------------

## 10) Security implications of the new model

### 10.1 What is now safer

The current design removes the main old leak path:

- raw runtime secrets are no longer injected into Terraform-managed Lambda env
  vars
- Terraform state does not need to carry those secrets as active deploy inputs

### 10.2 What still needs operational care

Even with the new model, you still need to treat these as sensitive:

- `terraform/terraform.tfvars.local`
- old Terraform state snapshots from before the migration
- any old Lambda configs that existed before the secret hardening change

If secrets were previously exposed through older state or config, they should
be rotated even after the new model is in place.

-------------------------------------------------------------------------------

## 11) Known operational coupling with GitHub Actions

Terraform deploy behavior is now coupled to the GitHub Actions runtime secret
resolution model in one important way:

- CI resolves an env-specific runtime secret ARN first
- CI syncs the secret contents
- CI passes that ARN into Terraform as `TF_VAR_runtime_secrets_arn`

That means the GitHub doc and Terraform doc must stay aligned on:

- env-specific secret variables
- `runtime_secret.sh` behavior
- OIDC role permissions for secret updates

For the GitHub-specific side of that process, see
[DEPLOYMENT_GITHUB_ACTIONS.md](/home/repos/twin/DEPLOYMENT_GITHUB_ACTIONS.md).

-------------------------------------------------------------------------------

## 12) Source of truth

For current implementation details, use:

- [deploy.sh](/home/repos/twin/scripts/deploy.sh)
- [destroy.sh](/home/repos/twin/scripts/destroy.sh)
- [runtime_secret.sh](/home/repos/twin/scripts/runtime_secret.sh)
- [variables.tf](/home/repos/twin/terraform/variables.tf)
- [main.tf](/home/repos/twin/terraform/main.tf)
- [terraform.tfvars](/home/repos/twin/terraform/terraform.tfvars)
- [prod.tfvars](/home/repos/twin/terraform/prod.tfvars)

This document is the current Terraform-side deployment guide. GitHub workflow,
repo variable, OIDC role, and environment behavior are documented in
[DEPLOYMENT_GITHUB_ACTIONS.md](/home/repos/twin/DEPLOYMENT_GITHUB_ACTIONS.md).
