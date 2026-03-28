# Deployment + Ops Runbook

This runbook describes the current deployment and operations model for `healthcare-saas-aws`.

It is the practical guide for:

- local infrastructure deployment
- production deployment behavior
- destroy and recreate behavior
- runtime verification
- the relationship between Terraform, App Runner, ECR, DynamoDB, Secrets Manager, and Route53

This document is intentionally operational. It is not a high-level architecture note.

## 1. Runtime topology

```text
Developer / GitHub Actions
  -> Terraform
      -> DynamoDB
      -> ECR
      -> App Runner roles
      -> Secrets Manager secret shells
      -> App Runner service
      -> Route53 custom domain

GitHub Actions / Local deploy script
  -> sync runtime secret values into AWS Secrets Manager
  -> build Docker image
  -> push image to ECR

App Runner
  -> public HTTPS ingress
  -> DynamoDB over AWS APIs
  -> Secrets Manager over AWS APIs
  -> Upstash Redis over public network
```

## 2. Environment model

There are two different environment systems:

### Terraform environments

- `dev`
- `prod`

These map to:

- `terraform/dev.tfvars`
- `terraform/prod.tfvars`
- Terraform workspaces `dev` and `prod`
- remote state keys:
  - `medinotes/dev/terraform.tfstate`
  - `medinotes/prod/terraform.tfstate`

### GitHub environments

- `healthcare-dev`
- `healthcare-prod`

These are used for:

- environment-scoped secrets
- environment-scoped `AWS_ROLE_ARN`
- GitHub OIDC trust identity
- branch restriction of deploy jobs

### Important distinction

For GitHub deploys, the Terraform target and the GitHub environment are related but not identical:

- Terraform `prod` goes with GitHub environment `healthcare-prod`
- Terraform `dev` goes with GitHub environment `healthcare-dev`

## 3. Current production resource names

Production currently uses these important names:

- App Runner service:
  - `consultation-app-service`
- App Runner URL:
  - `ymwpjvxcjn.ap-southeast-1.awsapprunner.com`
- ECR repository:
  - `consultation-app`
- DynamoDB table:
  - `medinotes-prod-memory`
- custom domain:
  - `medinotes.agentairg.site`
- secret prefix:
  - `medinotes-prod/app/*`

These names matter because production was adopted from an existing manual deployment and is now managed by Terraform.

## 4. Required runtime configuration

The deployed service needs both non-secret configuration and secret values.

### Non-secret runtime variables

Provided as App Runner environment variables:

- `NODE_ENV`
- `AWS_REGION`
- `DYNAMODB_TABLE_NAME`
- `GEMINI_API_URL`
- `DEEPSEEK_API_URL`
- `GROK_API_URL`
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
- `NEXT_PUBLIC_CLERK_JWT_TEMPLATE`
- `RESEND_FROM`

### Runtime secret values

Provided through AWS Secrets Manager and injected into App Runner by ARN:

- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `DEEPSEEK_API_KEY`
- `GROK_API_KEY`
- `RESEND_API_KEY`
- `CLERK_SECRET_KEY`
- `CLERK_JWKS_URL`
- `BRAVE_API_KEY`
- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`

### Local development-only memory variables

For local DynamoDB Local testing:

- `DYNAMODB_TABLE_NAME`
- `DYNAMODB_ENDPOINT_URL=http://localhost:8001`
- `AWS_REGION`
- dummy AWS credentials are acceptable

### Deployed AWS rule

In AWS runtime:

- `DYNAMODB_ENDPOINT_URL` must be unset

The service should use real AWS DynamoDB through its runtime IAM role.

## 5. Local development runbook

### Step 1: start DynamoDB Local

```bash
docker compose -f docker-compose.local.yml up -d
```

### Step 2: set local memory env

```bash
export DYNAMODB_TABLE_NAME=medinotes-memory
export DYNAMODB_ENDPOINT_URL=http://localhost:8001
export AWS_REGION=ap-southeast-1
export AWS_ACCESS_KEY_ID=dummy
export AWS_SECRET_ACCESS_KEY=dummy
```

### Step 3: create the local memory table

```bash
bash tools/create_memory_table.sh medinotes-memory
```

### Step 4: run the app locally

```bash
npm run dev
```

## 6. Local infrastructure deploy runbook

Use:

```bash
./scripts/deploy.sh dev
./scripts/deploy.sh prod
```

### What the local deploy wrapper does

For the selected environment, [deploy.sh](/home/repos/healthcare-saas-aws/scripts/deploy.sh) performs:

1. loads `.env`
2. loads `.env.local`
3. validates the selected tfvars file
4. bootstraps the Terraform backend bucket and lock table if needed
5. initializes Terraform with the correct remote state key
6. selects or creates the matching Terraform workspace
7. applies infrastructure prerequisites and configuration
8. syncs runtime secret values into AWS Secrets Manager
9. builds and pushes the Docker image to ECR
10. waits for App Runner rollout completion
11. verifies the `/health` endpoint

### Why secret sync happens before the image rollout

This ordering ensures the service configuration and secrets are already correct before App Runner picks up the new image. That avoids rolling out a new image against stale runtime configuration.

## 7. First deploy behavior

On the first deploy for an environment:

1. backend state is initialized
2. the workspace is created or selected
3. Terraform creates prerequisite infrastructure
4. secret shells are created in Secrets Manager
5. actual secret values are written into those secrets
6. the image is pushed to ECR
7. App Runner is created or finalized
8. health is verified

For healthcare production, the current stack is already past first deploy. The first-deploy path matters mostly for `dev` or full recreate scenarios.

## 8. Existing-service deploy behavior

For the current production service, deploys are existing-service deploys, not greenfield creates.

Current model:

1. Terraform reconciles infrastructure and service configuration
2. deploy script syncs secrets
3. Docker image is built and pushed
4. App Runner auto-deploy rolls out the new image
5. the script waits until App Runner returns to `RUNNING`

That is the normal redeploy path now.

## 9. GitHub deployment runbook

Current workflows:

- [ci.yml](/home/repos/healthcare-saas-aws/.github/workflows/ci.yml)
- [deploy.yml](/home/repos/healthcare-saas-aws/.github/workflows/deploy.yml)
- [destroy.yml](/home/repos/healthcare-saas-aws/.github/workflows/destroy.yml)

### Current automatic deploy behavior

- push to `healthcare-saas-aws`
  - runs `Test`
  - runs `Docker Build`
  - runs `Deploy / prod`

`dev` is currently manual-only. It is still a supported environment, but not an automatic push target.

### Deploy workflow order

The reusable deploy workflow performs:

1. checkout
2. AWS credential setup from environment-scoped `AWS_ROLE_ARN`
3. Terraform setup
4. run `scripts/deploy.sh` for the target environment

Inside `scripts/deploy.sh`, the ordered steps continue as described in section 6.

### Destroy workflow behavior

Destroy is manual-only and requires:

- explicit target environment
- exact confirmation string `DESTROY`

The workflow then runs `scripts/destroy.sh` in the correct GitHub environment.

## 10. Destroy runbook

Use locally:

```bash
./scripts/destroy.sh dev
./scripts/destroy.sh prod
```

### What the destroy wrapper does

For the selected environment, [destroy.sh](/home/repos/healthcare-saas-aws/scripts/destroy.sh) performs:

1. validates the tfvars file
2. bootstraps the Terraform backend
3. initializes Terraform
4. selects the correct workspace
5. empties the ECR repository
6. runs `terraform destroy`

### Why the ECR cleanup exists

AWS ECR will not delete a non-empty repository. The script clears images first so destroy succeeds cleanly.

### Why secret names do not block recreation anymore

The Terraform secret resources use:

- `recovery_window_in_days = 0`

That prevents the old failure mode where a destroy would leave secrets “scheduled for deletion” and block the next recreate.

## 11. One-time adoption of the manual production service

Production was not built entirely from scratch with Terraform. The current stack adopted an existing manual App Runner service and ECR repository into Terraform state.

That is why:

- the service name is `consultation-app-service`
- the ECR repository is `consultation-app`
- `prod.tfvars` includes explicit overrides for those names

Operational takeaway:

- production should now be treated as Terraform-managed
- future redeploys should go through `deploy.sh` or GitHub Actions
- future destroys should go through `destroy.sh` or the destroy workflow

## 12. Verification checklist

### App Runner health

```bash
curl -fsS https://medinotes.agentairg.site/health
```

Expected:

```json
{"status":"healthy"}
```

### DynamoDB memory existence

```bash
aws dynamodb describe-table --region ap-southeast-1 --table-name medinotes-prod-memory
aws dynamodb scan --region ap-southeast-1 --table-name medinotes-prod-memory --max-items 10
```

Use `scan` as the real confirmation that records exist. `describe-table` item counts can lag.

### Route53/custom domain

```bash
dig medinotes.agentairg.site +short
curl -I https://medinotes.agentairg.site
```

### Terraform state sanity

```bash
terraform -chdir=terraform workspace show
terraform -chdir=terraform state list
terraform -chdir=terraform plan -var-file=prod.tfvars
```

## 13. Common failure modes

### App Runner deploy succeeds but patient history is empty

Check:

- whether DynamoDB has records
- whether memory writes failed late in the summary pipeline
- whether patient-name normalization caused lookup mismatch

### Deploy fails after ECR push

Check:

- App Runner rollout status
- image build args
- health endpoint
- runtime secret sync

### Destroy fails on ECR

Check:

- whether the repository still contains images
- whether the wrapper script ran instead of raw Terraform destroy

### Recreate fails on Secrets Manager names

That should no longer happen under the current configuration. If it does, inspect whether the secret resource names or manual AWS operations bypassed the Terraform-managed path.

## 14. Operational source of truth

For this app today:

- Terraform is the infrastructure source of truth
- GitHub Actions is the CI/CD execution path
- Secrets Manager is the runtime secret source
- DynamoDB is the long-term patient-memory source
- App Runner is the application runtime

That is the intended operating model going forward.

