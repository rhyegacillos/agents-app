# Terraform Infrastructure

This directory is the infrastructure source of truth for the current PostgreSQL-based AWS deployment.

It provisions:

- VPC with public and private subnets
- NAT gateway for private outbound access
- security groups
- RDS PostgreSQL
- AWS-managed RDS master credentials in Secrets Manager
- app runtime secrets in Secrets Manager
- ECR repository for the application image
- App Runner service
- App Runner VPC connector for private RDS access
- Route 53/App Runner custom-domain association outputs

## 1. Environment Model

Terraform environments are split by var-file, workspace, and state key.

Current supported var-files:

- `terraform/dev.tfvars`
- `terraform/test.tfvars`
- `terraform/prod.tfvars`

Each environment is expected to have:

- its own Terraform workspace
- its own remote state key
- its own named AWS resources

Example state keys:

- `ideagen/dev/terraform.tfstate`
- `ideagen/test/terraform.tfstate`
- `ideagen/prod/terraform.tfstate`

## 2. Backend Bootstrap

Terraform remote state backend infrastructure is created automatically by [scripts/bootstrap_tf_backend.sh](/home/repos/ideagen-saas-aws/scripts/bootstrap_tf_backend.sh).

Bootstrap creates or reuses:

- S3 bucket: `ideagen-terraform-state-<account-id>-<region>`
- DynamoDB table: `ideagen-terraform-locks`

The local deploy and destroy wrappers already call this script before `terraform init`.

## 3. Database and Secret Model

### RDS

The Postgres database is created by Terraform.

Important behavior:

- the RDS master password is AWS-managed
- Terraform outputs the master secret ARN
- the app does not use that master secret directly

### App runtime secrets

The app runtime secrets are separate Secrets Manager entries, including:

- `DATABASE_URL_PROD`
- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `DEEPSEEK_API_KEY`
- `GROK_API_KEY`
- `RESEND_API_KEY`

Terraform creates the secret containers/resources.
Local scripts or GitHub Actions write the actual secret values.

This keeps secret values out of Terraform state.

## 4. Current Deploy Flow

### First deploy

On the first deploy for an environment:

1. backend state is initialized
2. Terraform workspace is selected
3. the deploy wrapper checks whether App Runner is already managed in state
4. if not, it performs a targeted bootstrap for prerequisite infrastructure:
   - VPC
   - subnets
   - NAT
   - security groups
   - RDS
   - ECR
   - IAM roles
   - App Runner VPC connector
   - secret metadata
5. runtime secrets are synced to Secrets Manager
6. Docker image is built and pushed to ECR
7. Terraform creates App Runner
8. deploy wrapper waits for rollout/health

### Subsequent redeploys

On normal redeploys:

1. backend/workspace are initialized as usual
2. bootstrap is skipped because App Runner is already managed in state
3. runtime secrets are synced
4. Docker image is rebuilt and pushed
5. Terraform updates App Runner config if needed
6. if the service is already `RUNNING`, the wrapper calls `start-deployment`
7. if Terraform has already triggered a rollout, the wrapper waits instead of starting a second deployment
8. wrapper waits for `/health`

This behavior is important because the earlier “disable App Runner then re-enable it” pattern is no longer used.

## 5. Local Commands

### Deploy

Use the environment wrapper:

```bash
./scripts/deploy.sh dev
./scripts/deploy.sh prod
```

What it automatically selects:

- the Terraform workspace
- the correct remote state key
- the matching `terraform/<environment>.tfvars`

### Destroy

```bash
./scripts/destroy.sh dev
./scripts/destroy.sh prod
```

That destroys all Terraform-managed resources in the selected environment.

## 6. Manual Terraform Usage

If you need to operate Terraform directly:

```bash
./scripts/bootstrap_tf_backend.sh --project-name ideagen --region ap-southeast-1

cd terraform
terraform init \
  -reconfigure \
  -backend-config="bucket=<bucket-from-bootstrap>" \
  -backend-config="dynamodb_table=<lock-table-from-bootstrap>" \
  -backend-config="key=ideagen/dev/terraform.tfstate" \
  -backend-config="region=ap-southeast-1"

terraform workspace new dev || terraform workspace select dev
terraform plan -var-file=dev.tfvars
```

## 7. Local Secret Sync

Local runtime secret sync is handled by:

- [scripts/sync_app_secrets_local.sh](/home/repos/ideagen-saas-aws/scripts/sync_app_secrets_local.sh)
- [scripts/sync_app_secrets.sh](/home/repos/ideagen-saas-aws/scripts/sync_app_secrets.sh)

The local wrapper:

- loads `.env`
- reads Terraform outputs
- fetches the AWS-managed RDS master password
- builds `DATABASE_URL_PROD`
- writes app secrets into Secrets Manager

Example:

```bash
./scripts/sync_app_secrets_local.sh \
  --env-file .env \
  --environment dev \
  --tfvars-file terraform/dev.tfvars \
  --region ap-southeast-1
```

## 8. Custom Domains

Custom domain association is driven by `app_runner_custom_domain` in the environment var-file.

Terraform outputs:

- `app_runner_custom_domain_dns_target`
- `app_runner_custom_domain_validation_records`
- `app_runner_custom_domain_status`

This supports:

- domain validation
- DNS target visibility
- post-deploy verification

## 9. GitHub Actions Integration

GitHub Actions workflows use this Terraform stack directly.

Relevant workflows:

- [.github/workflows/ci.yml](/home/repos/ideagen-saas-aws/.github/workflows/ci.yml)
- [.github/workflows/deploy.yml](/home/repos/ideagen-saas-aws/.github/workflows/deploy.yml)
- [.github/workflows/destroy.yml](/home/repos/ideagen-saas-aws/.github/workflows/destroy.yml)

Deploy workflow behavior:

- runs tests first
- bootstraps backend
- initializes Terraform
- selects workspace
- syncs secrets
- builds/pushes image
- applies App Runner
- waits for stable service / health

Destroy workflow behavior:

- manual only
- explicit confirmation required

## 10. Required GitHub Configuration

### GitHub environment variables

- `PROJECT_NAME`
- `DEFAULT_AWS_REGION`
- `ALLOWED_HOSTS`

### GitHub environment secrets

- `AWS_ROLE_ARN`
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
- `CLERK_JWKS_URL`
- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `GEMINI_API_URL`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_API_URL`
- `GROK_API_KEY`
- `GROK_API_URL`
- `RESEND_API_KEY`
- `EMAIL_FROM`

## 11. Operational Notes

- Terraform creates infrastructure and secret containers, not the secret values themselves
- App Runner and RDS should be treated as long-lived resources per environment
- routine redeploys should update the existing service, not delete and recreate it
- do not flip a single shared `terraform.tfvars` between environments; use the per-env var-files
