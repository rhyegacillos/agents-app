# Terraform Infrastructure

This directory is the infrastructure source of truth for the AWS deployment of `healthcare-saas-aws`.

It provisions:

- DynamoDB for long-term memory persistence
- ECR repository for the application image
- App Runner service
- App Runner IAM roles for ECR pull and runtime access
- application secrets in Secrets Manager
- Route53/App Runner custom-domain association for production

## Environment model

Supported environments:

- `terraform/dev.tfvars`
- `terraform/prod.tfvars`

Each environment uses:

- its own Terraform workspace
- its own remote state key
- its own named AWS resources

Example state keys:

- `medinotes/dev/terraform.tfstate`
- `medinotes/prod/terraform.tfstate`

## Backend bootstrap

Remote state backend infrastructure is created automatically inside [deploy.sh](/home/repos/healthcare-saas-aws/scripts/deploy.sh) and [destroy.sh](/home/repos/healthcare-saas-aws/scripts/destroy.sh).

Bootstrap creates or reuses:

- S3 bucket: `medinotes-terraform-state-<account-id>-<region>`
- DynamoDB table: `medinotes-terraform-locks`

## Secrets model

Terraform creates the secret containers only.

Actual secret values are written by:

- GitHub Actions deploy workflow
- [deploy.sh](/home/repos/healthcare-saas-aws/scripts/deploy.sh)

This keeps secret values out of Terraform state.

## GitHub environments

The workflows expect:

- `healthcare-dev`
- `healthcare-prod`

These environments now use the same dedicated healthcare deploy role:

- `arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`

This ARN is intentionally shared by both healthcare environments.

Each environment should provide at least:

- `AWS_ROLE_ARN`
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
- `NEXT_PUBLIC_CLERK_JWT_TEMPLATE`
- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `DEEPSEEK_API_KEY`
- `GROK_API_KEY`
- `RESEND_API_KEY`
- `RESEND_FROM`
- `CLERK_SECRET_KEY`
- `CLERK_JWKS_URL`
- `BRAVE_API_KEY`
- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`
- `GEMINI_API_URL`
- `DEEPSEEK_API_URL`
- `GROK_API_URL`

The local source of truth for re-syncing the environment-scoped role ARN is:

- `HEALTHCARE_DEV_AWS_ROLE_ARN`
- `HEALTHCARE_PROD_AWS_ROLE_ARN`

Those values are consumed by [sync_github_environments.sh](/home/repos/healthcare-saas-aws/tools/sync_github_environments.sh).

## IAM roles and permissions

This stack uses three distinct IAM role types.

### 1. GitHub Actions deploy role

Current live role:

- `github-actions-healthcare-deploy`
- `arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`

This same ARN is intentionally used in both:

- `healthcare-dev`
- `healthcare-prod`

Trust policy restrictions:

- federated principal:
  - `arn:aws:iam::348375262167:oidc-provider/token.actions.githubusercontent.com`
- audience:
  - `token.actions.githubusercontent.com:aud = sts.amazonaws.com`
- allowed `sub` values:
  - `repo:rhyegacillos/agents-app:environment:healthcare-dev`
  - `repo:rhyegacillos/agents-app:environment:healthcare-prod`

Current attached managed policies:

- `AmazonEC2ContainerRegistryPowerUser`
- `AWSAppRunnerFullAccess`
- `SecretsManagerReadWrite`
- `AmazonDynamoDBFullAccess`
- `AmazonRoute53FullAccess`
- `AmazonS3FullAccess`
- `IAMReadOnlyAccess`

Current inline policy:

- `github-actions-healthcare-iam`

Current inline actions:

- `iam:CreateRole`
- `iam:DeleteRole`
- `iam:AttachRolePolicy`
- `iam:DetachRolePolicy`
- `iam:PutRolePolicy`
- `iam:DeleteRolePolicy`
- `iam:GetRole`
- `iam:GetRolePolicy`
- `iam:ListRolePolicies`
- `iam:ListAttachedRolePolicies`
- `iam:UpdateAssumeRolePolicy`
- `iam:PassRole`
- `iam:TagRole`
- `iam:UntagRole`
- `iam:ListInstanceProfilesForRole`
- `sts:GetCallerIdentity`

Purpose:

- access Terraform remote state
- create and destroy healthcare AWS resources
- sync runtime secrets into AWS Secrets Manager
- build and push images to ECR
- inspect App Runner deployments and custom domains

### 2. App Runner ECR access role

Terraform creates:

- `${project_name}-${environment}-apprunner-ecr-access`

Assumed by:

- `build.apprunner.amazonaws.com`

Policy attached:

- `service-role/AWSAppRunnerServicePolicyForECRAccess`

Purpose:

- allow App Runner to pull from the managed ECR repository

### 3. App Runner runtime role

Terraform creates:

- `${project_name}-${environment}-apprunner-instance`

Assumed by:

- `tasks.apprunner.amazonaws.com`

Permissions granted:

- Secrets Manager read:
  - `secretsmanager:GetSecretValue`
  - `secretsmanager:DescribeSecret`
- DynamoDB access:
  - `dynamodb:BatchWriteItem`
  - `dynamodb:DeleteItem`
  - `dynamodb:DescribeTable`
  - `dynamodb:GetItem`
  - `dynamodb:PutItem`
  - `dynamodb:Query`
  - `dynamodb:Scan`
  - `dynamodb:UpdateItem`
- KMS decrypt only via Secrets Manager:
  - `kms:Decrypt`

This runtime role is scoped to:

- the healthcare app secret ARNs created in `secrets.tf`
- the healthcare DynamoDB table ARN and index ARNs

### 4. Optional Terraform management of the GitHub role

`terraform/github_actions.tf` can optionally attach broad AWS-managed policies to an existing GitHub role when:

- `manage_github_actions_role_policies = true`
- `github_actions_role_name` is set

Current code attaches:

- `AmazonEC2ContainerRegistryPowerUser`
- `AWSAppRunnerFullAccess`
- `SecretsManagerReadWrite`
- `AmazonDynamoDBFullAccess`
- `AmazonRoute53FullAccess`
- `AmazonS3FullAccess`
- `IAMFullAccess`

The live manually created role is slightly narrower because it uses:

- `IAMReadOnlyAccess`
- plus the inline policy `github-actions-healthcare-iam`

Treat the live AWS role as the operational source of truth unless Terraform is explicitly used to take over that role configuration.

## First deploy

On the first deploy for an environment:

1. [deploy.sh](/home/repos/healthcare-saas-aws/scripts/deploy.sh) initializes the backend state
2. `deploy.sh` selects the Terraform workspace
3. `deploy.sh` creates prerequisite infrastructure without App Runner:
   - DynamoDB
   - ECR
   - IAM roles
   - App Runner autoscaling config
   - secret metadata
4. `deploy.sh` syncs runtime secrets
5. `deploy.sh` builds and pushes the Docker image to ECR
6. `deploy.sh` runs the full Terraform apply to create App Runner
7. `deploy.sh` waits for `/health`

For local runs, `deploy.sh` auto-loads:

- `.env`
- `.env.local`

## Subsequent deploys

On normal redeploys:

1. [deploy.sh](/home/repos/healthcare-saas-aws/scripts/deploy.sh) initializes the backend and workspace
2. `deploy.sh` bootstraps prerequisite infrastructure and secret shells
3. `deploy.sh` syncs runtime secrets into AWS Secrets Manager
4. `deploy.sh` applies infrastructure and App Runner config before image push
5. `deploy.sh` builds and pushes the Docker image to ECR
6. App Runner auto-deploy rolls out the new image
7. `deploy.sh` waits for `/health`

## Destroy

Use [destroy.sh](/home/repos/healthcare-saas-aws/scripts/destroy.sh):

```bash
./scripts/destroy.sh dev
./scripts/destroy.sh prod
```

The wrapper:

- bootstraps the backend
- selects the workspace
- empties the ECR repository
- runs `terraform destroy`

## Adopt an existing manual production deployment

The current live manual healthcare deployment uses:

- App Runner service: `consultation-app-service`
- App Runner ARN:
  - `arn:aws:apprunner:ap-southeast-1:348375262167:service/consultation-app-service/6b425a10d0a7447b98768fbe4846b733`
- ECR repository: `consultation-app`
- custom domain: `medinotes.agentairg.site`
- Route53 hosted zone ID:
  - `Z05037913IHZ03VIE2PMO`

The `prod` tfvars file is now aligned to those live names.

Use this exact one-time adoption sequence before handing deployment and destroy over to GitHub Actions:

```bash
cd /home/repos/healthcare-saas-aws

./scripts/deploy.sh prod --init-only

terraform -chdir=terraform import -var-file=prod.tfvars \
  aws_ecr_repository.app \
  consultation-app

terraform -chdir=terraform import -var-file=prod.tfvars \
  'aws_apprunner_service.app[0]' \
  'arn:aws:apprunner:ap-southeast-1:348375262167:service/consultation-app-service/6b425a10d0a7447b98768fbe4846b733'

terraform -chdir=terraform import -var-file=prod.tfvars \
  'aws_apprunner_custom_domain_association.app[0]' \
  'medinotes.agentairg.site,arn:aws:apprunner:ap-southeast-1:348375262167:service/consultation-app-service/6b425a10d0a7447b98768fbe4846b733'

terraform -chdir=terraform import -var-file=prod.tfvars \
  aws_route53_record.app_runner_custom_domain \
  'Z05037913IHZ03VIE2PMO_medinotes.agentairg.site_CNAME'
```

After import:

```bash
terraform -chdir=terraform plan -var-file=prod.tfvars
```

Expect Terraform to create the resources that did not exist in the manual stack:

- DynamoDB table
- Secrets Manager secret shells
- Terraform-managed App Runner IAM roles
- Terraform-managed App Runner autoscaling configuration

Then run the first Terraform-managed deploy:

```bash
./scripts/deploy.sh prod
```

That first managed deploy will:

- create the missing DynamoDB and Secrets Manager resources
- sync the current runtime secrets into AWS Secrets Manager
- update the App Runner service to the Terraform-managed runtime model after the secret values already exist
- keep using the existing App Runner service and ECR repository

After that first managed deploy succeeds:

- GitHub Actions can redeploy it
- [destroy.sh](/home/repos/healthcare-saas-aws/scripts/destroy.sh) can destroy it
- [deploy.sh](/home/repos/healthcare-saas-aws/scripts/deploy.sh) can recreate it from scratch later

## Script layout

For infrastructure operations, `scripts/` intentionally contains only:

- [deploy.sh](/home/repos/healthcare-saas-aws/scripts/deploy.sh)
- [destroy.sh](/home/repos/healthcare-saas-aws/scripts/destroy.sh)

Non-deploy helper utilities live outside that folder:

- [create_memory_table.sh](/home/repos/healthcare-saas-aws/tools/create_memory_table.sh)
- [sync_github_environments.sh](/home/repos/healthcare-saas-aws/tools/sync_github_environments.sh)

## Local-only DynamoDB

Local development continues to use DynamoDB Local via `DYNAMODB_ENDPOINT_URL`.

AWS deployments must not set `DYNAMODB_ENDPOINT_URL`.
