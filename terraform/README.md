# Terraform Infrastructure Guide

This directory is the infrastructure source of truth for the AWS deployment of `healthcare-saas-aws`.

It documents the current implemented stack, not a hypothetical one. The production deployment has already been aligned to this model, including adoption of an existing manual App Runner service into Terraform state.

## 1. What Terraform owns in this repo

The Terraform stack manages the AWS resources required to run the healthcare application as a durable AWS service.

Current managed resource categories:

- DynamoDB table for long-term patient memory
- ECR repository for the application image
- App Runner service
- App Runner autoscaling configuration
- App Runner IAM roles
- Secrets Manager secret containers
- Route53 custom-domain record
- App Runner custom-domain association
- optional GitHub Actions role policy attachments when enabled

Terraform does not manage:

- actual secret values
- Upstash resources
- model-provider accounts
- Clerk tenant configuration
- Resend tenant configuration

## 2. Why this stack is simpler than `ideagen`

`healthcare-saas-aws` does not currently need:

- RDS
- VPC
- private subnets
- NAT gateway
- App Runner VPC connector

That is intentional.

The application’s durable data path is:

- DynamoDB
- Secrets Manager
- Upstash Redis

and all of those are reachable without building a private-network topology similar to the `ideagen` stack.

## 3. Environment model

The Terraform environments are:

- `dev`
- `prod`

They map to:

- [dev.tfvars](/home/repos/healthcare-saas-aws/terraform/dev.tfvars)
- [prod.tfvars](/home/repos/healthcare-saas-aws/terraform/prod.tfvars)

Each environment uses:

- its own Terraform workspace
- its own state key
- its own named AWS resources

Current remote state layout:

- `medinotes/dev/terraform.tfstate`
- `medinotes/prod/terraform.tfstate`

## 4. Backend bootstrap

Remote state backend infrastructure is created or reused by:

- [deploy.sh](/home/repos/healthcare-saas-aws/scripts/deploy.sh)
- [destroy.sh](/home/repos/healthcare-saas-aws/scripts/destroy.sh)

Current backend resources:

- S3 bucket:
  - `medinotes-terraform-state-<account-id>-<region>`
- DynamoDB lock table:
  - `medinotes-terraform-locks`

The scripts ensure:

- bucket existence
- versioning
- SSE encryption
- public access block
- lock-table existence

before running `terraform init`.

## 5. Current production resource naming

Production was adopted from a live manual deployment, so `prod` uses explicit names that match the pre-existing resources.

Current production values in [prod.tfvars](/home/repos/healthcare-saas-aws/terraform/prod.tfvars):

- `project_name = "medinotes"`
- `environment = "prod"`
- `dynamodb_table_name = "medinotes-prod-memory"`
- `ecr_repository_name = "consultation-app"`
- `app_runner_service_name = "consultation-app-service"`
- `app_runner_custom_domain = "medinotes.agentairg.site"`
- `app_runner_custom_domain_dns_target_override = "ymwpjvxcjn.ap-southeast-1.awsapprunner.com"`

This override is important because the service was adopted into Terraform rather than created from scratch under a brand-new generated name.

## 6. Current development resource naming

`dev` uses the standard generated naming model unless overridden:

- DynamoDB table:
  - `medinotes-dev-memory`
- App Runner service:
  - `medinotes-dev-service`

There is no custom domain configured by default in `dev`.

## 7. Resource-by-resource ownership

### 7.1 DynamoDB

Main resource:

- [aws_dynamodb_table.memory](/home/repos/healthcare-saas-aws/terraform/main.tf)

Current design:

- billing mode: `PAY_PER_REQUEST`
- partition key: `pk`
- sort key: `sk`
- GSI: `doc_id-index`
- optional point-in-time recovery controlled by variable

Purpose:

- stores patient memory documents with embeddings and metadata
- backs patient-history retrieval and assistant recall

### 7.2 ECR

Resources:

- `aws_ecr_repository.app`
- `aws_ecr_lifecycle_policy.app`

Current behavior:

- mutable tags
- image scan on push enabled
- `force_delete = true`
- lifecycle policy for image retention

Purpose:

- stores the App Runner image source
- receives `latest` and SHA-tagged pushes from deploys

### 7.3 App Runner

Resources:

- `aws_apprunner_auto_scaling_configuration_version.main`
- `aws_apprunner_service.app`
- `aws_apprunner_custom_domain_association.app`

Current design:

- public service
- ECR image source
- App Runner auto deployments enabled from ECR push
- health checks configured through variables
- runtime environment variables for non-secret config
- runtime environment secrets by ARN for secret values

Purpose:

- runs the combined Next.js + FastAPI application

### 7.4 Route53

Resources:

- `data.aws_route53_zone.app_runner_custom_domain`
- `aws_route53_record.app_runner_custom_domain`

Purpose:

- ensures `medinotes.agentairg.site` is managed by Terraform
- avoids stale DNS after service recreation

### 7.5 Secrets Manager

Resources are defined in:

- [secrets.tf](/home/repos/healthcare-saas-aws/terraform/secrets.tf)

Important design choice:

- Terraform creates secret containers only
- secret values are written later by deploy tooling

Current managed secret shells include:

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

All use:

- `recovery_window_in_days = 0`

That setting is deliberate. It allows a destroy/recreate cycle to reuse the same secret names immediately instead of getting stuck on AWS’s default delayed deletion window.

## 8. Secrets model

This stack intentionally separates:

- infrastructure definition
- secret value management

### 8.1 What Terraform does

Terraform defines:

- the existence of the secret
- the secret ARN
- which App Runner runtime variable points to which secret ARN

### 8.2 What Terraform does not do

Terraform does not store the secret value.

That is critical because otherwise:

- secrets would land in Terraform state
- backend state would become a secret store
- destroy/recreate and environment syncing would be harder to manage safely

### 8.3 Who writes the actual secret values

The real values are written by:

- local deploy:
  - [deploy.sh](/home/repos/healthcare-saas-aws/scripts/deploy.sh)
- GitHub Actions deploy:
  - [deploy.yml](/home/repos/healthcare-saas-aws/.github/workflows/deploy.yml)

Both ultimately sync to AWS Secrets Manager before the runtime image rollout completes.

## 9. IAM roles in this stack

This stack uses several distinct IAM roles. They serve different purposes and should not be conflated.

### 9.1 GitHub Actions deploy role

Current live role:

- `github-actions-healthcare-deploy`
- `arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`

Used by:

- GitHub environment `healthcare-dev`
- GitHub environment `healthcare-prod`

The same ARN is intentionally shared by both healthcare GitHub environments.

Trust restrictions:

- OIDC provider:
  - `arn:aws:iam::348375262167:oidc-provider/token.actions.githubusercontent.com`
- audience:
  - `sts.amazonaws.com`
- allowed subjects:
  - `repo:rhyegacillos/agents-app:environment:healthcare-dev`
  - `repo:rhyegacillos/agents-app:environment:healthcare-prod`

### 9.2 App Runner ECR access role

Terraform resource:

- `aws_iam_role.apprunner_ecr_access`

Purpose:

- allows App Runner build infrastructure to pull the application image from ECR

Assumed by:

- `build.apprunner.amazonaws.com`

### 9.3 App Runner runtime role

Terraform resource:

- `aws_iam_role.apprunner_instance`

Purpose:

- grants the running application access to:
  - Secrets Manager
  - DynamoDB

Assumed by:

- `tasks.apprunner.amazonaws.com`

### 9.4 Optional Terraform takeover of GitHub role policy attachments

[github_actions.tf](/home/repos/healthcare-saas-aws/terraform/github_actions.tf) allows Terraform to manage policy attachments for an existing GitHub role when explicitly enabled.

This is optional. The live manually created healthcare GitHub role remains the operational source of truth unless Terraform is intentionally used to take over that role configuration.

## 10. Deploy workflow semantics

The deploy flow is implemented in:

- [scripts/deploy.sh](/home/repos/healthcare-saas-aws/scripts/deploy.sh)

### 10.1 Why the script exists

The script provides a single ordered deployment entry point for:

- local deploys
- GitHub Actions deploys

so the deploy logic stays consistent.

### 10.2 What `deploy.sh` does

At a high level the script:

1. loads `.env` and `.env.local` for local runs
2. validates and reads the chosen tfvars file
3. bootstraps the Terraform backend
4. initializes Terraform
5. selects or creates the Terraform workspace
6. applies prerequisite infrastructure
7. syncs runtime secrets into Secrets Manager
8. builds the Docker image
9. pushes the image to ECR
10. completes or confirms App Runner rollout
11. checks the health endpoint

### 10.3 First deploy versus existing-service deploy

The script distinguishes between:

- first deploy of a new environment
- redeploy of an existing App Runner service

For the adopted production stack, this matters because the service already exists and Terraform now manages it rather than creating a parallel service.

## 11. Destroy workflow semantics

The destroy flow is implemented in:

- [scripts/destroy.sh](/home/repos/healthcare-saas-aws/scripts/destroy.sh)

### 11.1 What `destroy.sh` does

The script:

1. validates the tfvars file
2. bootstraps the remote backend
3. initializes Terraform
4. selects the correct workspace
5. empties the ECR repository first
6. runs `terraform destroy`

### 11.2 Why the ECR cleanup exists

Destroying an ECR repository often fails when images still exist. The script empties the repository first so teardown can succeed cleanly.

### 11.3 Why secrets can be recreated immediately

`recovery_window_in_days = 0` on the Secrets Manager resources is what prevents a destroy/recreate cycle from failing on:

- “secret already scheduled for deletion”

## 12. Local development versus AWS runtime

### 12.1 Local

Local development may use:

- DynamoDB Local
- `.env`
- `.env.local`

and a developer may set:

- `DYNAMODB_ENDPOINT_URL=http://localhost:8001`

### 12.2 AWS

Deployed AWS environments must not set `DYNAMODB_ENDPOINT_URL`.

In AWS, the app should instead use:

- real DynamoDB
- App Runner runtime IAM role
- Secrets Manager-backed secret resolution

## 13. GitHub environment integration

The Terraform stack is paired with these GitHub environments:

- `healthcare-dev`
- `healthcare-prod`

The detailed environment setup and branch restrictions are documented in:

- [healthcare_github_environment_setup.md](/home/repos/healthcare-saas-aws/healthcare_github_environment_setup.md)

At a high level:

- push to `healthcare-saas-aws` auto-deploys to `prod`
- `dev` remains manual
- both GitHub environments use the dedicated healthcare deploy role

## 14. Validation and current status

This stack has already progressed beyond design-only status.

Current achieved state:

- Terraform stack exists in code
- prod deployment is live
- prod GitHub deploy path is working
- DynamoDB-backed patient memory is active
- Secrets Manager-backed runtime secret sync is active
- Route53 custom-domain ownership is in Terraform

Remaining work is operational and evolutionary, not foundational:

- keep docs current as the app evolves
- continue tightening IAM scope if desired
- improve DynamoDB query strategy over time if scale demands it

