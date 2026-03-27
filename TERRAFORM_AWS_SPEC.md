# Terraform AWS Spec for `healthcare-saas-aws`

## Goal

Create a Terraform-based AWS deployment for `healthcare-saas-aws` that is structurally similar to `ideagen-saas-aws`, but uses DynamoDB instead of RDS.

The stack must provision and manage:

- ECR repository for the application image
- App Runner service for the web app
- DynamoDB for persistent memory storage
- Secrets Manager for runtime secrets
- Route53 for the custom domain
- IAM roles and policies for App Runner and GitHub Actions deploys

This spec is for the first production-ready infrastructure version. It is not the implementation itself.

## Current Implementation Status

The following items are already implemented or provisioned:

- Terraform stack created under `terraform/`
- GitHub Actions workflows created under `.github/workflows/`
- GitHub environments created:
  - `healthcare-dev`
  - `healthcare-prod`
- GitHub branch policies applied:
  - `healthcare-dev` -> `dev`
  - `healthcare-prod` -> `healthcare-saas-aws`
- dedicated AWS deploy role created:
  - `arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`
- both healthcare GitHub environments now contain `AWS_ROLE_ARN`
- local override keys added:
  - `HEALTHCARE_DEV_AWS_ROLE_ARN`
  - `HEALTHCARE_PROD_AWS_ROLE_ARN`
- live GitHub environments now both use:
  - `arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`
- live deploy role trust is restricted to:
  - `repo:rhyegacillos/agents-app:environment:healthcare-dev`
  - `repo:rhyegacillos/agents-app:environment:healthcare-prod`
- live deploy role currently has these attached managed policies:
  - `AmazonEC2ContainerRegistryPowerUser`
  - `AWSAppRunnerFullAccess`
  - `SecretsManagerReadWrite`
  - `AmazonDynamoDBFullAccess`
  - `AmazonRoute53FullAccess`
  - `AmazonS3FullAccess`
  - `IAMReadOnlyAccess`
- live deploy role currently has inline policy:
  - `github-actions-healthcare-iam`

The following items are implemented in code but still require live deployment validation:

- first Terraform apply for `dev`
- first Terraform apply for `prod`
- first GitHub Actions deploy on `dev`
- first GitHub Actions deploy on `healthcare-saas-aws`
- destroy workflow verification in both environments

## Design Principles

- Keep Terraform as the source of truth for infrastructure and DNS.
- Keep secrets in AWS Secrets Manager and GitHub environment secrets, not in Terraform state.
- Keep the stack simpler than `ideagen` where the application does not require private networking.
- Preserve the current application behavior:
  - App Runner serves the Next.js app
  - DynamoDB stores the memory vector documents
  - Upstash remains external and is not provisioned by Terraform
- Keep local development separate from AWS deployment:
  - local uses DynamoDB Local via `DYNAMODB_ENDPOINT_URL`
  - AWS deployment does not set `DYNAMODB_ENDPOINT_URL`

## Why This Differs from `ideagen`

`ideagen` needed:

- VPC
- private subnets
- DB subnet group
- RDS
- NAT gateway
- security groups for private DB access

`healthcare-saas-aws` does not need that for the current architecture because:

- DynamoDB is a managed regional service accessed over AWS APIs
- Secrets Manager is also accessed over AWS APIs
- Upstash is external
- App Runner can run publicly without a VPC connector for this app

So the recommended Terraform for this repo should **not** copy the full VPC/RDS footprint from `ideagen`. It should mirror the deployment shape, not the unnecessary network complexity.

## Proposed Terraform Layout

Create:

- `terraform/versions.tf`
- `terraform/backend.tf`
- `terraform/variables.tf`
- `terraform/main.tf`
- `terraform/secrets.tf`
- `terraform/github_actions.tf`
- `terraform/outputs.tf`
- `terraform/dev.tfvars`
- `terraform/prod.tfvars`
- `terraform/terraform.tfvars.example`
- `terraform/README.md`

Optional later:

- `terraform/test.tfvars`

## Resources

### 1. DynamoDB

Create one DynamoDB table for memory storage.

Recommended resource:

- `aws_dynamodb_table.memory`

Required table design:

- partition key: `pk` (String)
- sort key: `sk` (String)
- billing mode: `PAY_PER_REQUEST`

Recommended additional attributes/indexes:

- attribute: `doc_id` (String)
- GSI: `doc_id-index`
  - partition key: `doc_id`

Reason:

- current code already uses `pk` and `sk`
- current code also scans by `doc_id`
- adding a `doc_id` GSI gives a clean production path and avoids full-table scans for rename/delete/restore flows

Optional later:

- TTL attribute for soft-deleted cleanup if desired
- patient/date GSI if history screens need more efficient sorting without in-memory filtering

### 2. ECR

Create one ECR repository for the app image.

Resources:

- `aws_ecr_repository.app`
- `aws_ecr_lifecycle_policy.app`

Requirements:

- mutable tags for `latest`-style deploy flow
- `force_delete = true` so destroy works cleanly
- lifecycle policy to retain a bounded number of recent images

### 3. App Runner

Create one App Runner service sourced from ECR.

Resources:

- `aws_iam_role.apprunner_ecr_access`
- `aws_iam_role_policy_attachment.apprunner_ecr_access`
- `aws_iam_role.apprunner_instance`
- `aws_iam_role_policy.apprunner_instance_runtime`
- `aws_apprunner_auto_scaling_configuration_version.main`
- `aws_apprunner_service.app`

Requirements:

- public App Runner service
- source image from the managed ECR repository
- image tag variable, default `latest`
- runtime environment variables for non-secret config
- runtime secret references for secrets stored in Secrets Manager
- health check path configurable, default `/`
- CPU and memory configurable per environment
- auto deployments enabled from ECR pushes

Important:

- Since this app depends on DynamoDB and Secrets Manager only, no App Runner VPC connector should be included in the initial version.
- If future private AWS dependencies are added, VPC integration can be introduced later.

### 3a. IAM roles and permissions

This stack has three different IAM role categories and they should not be conflated.

#### GitHub Actions deploy role

Live role:

- `arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`

Used by:

- GitHub environment `healthcare-dev`
- GitHub environment `healthcare-prod`

Trust restrictions:

- federated principal:
  - `arn:aws:iam::348375262167:oidc-provider/token.actions.githubusercontent.com`
- audience:
  - `token.actions.githubusercontent.com:aud = sts.amazonaws.com`
- allowed subjects:
  - `repo:rhyegacillos/agents-app:environment:healthcare-dev`
  - `repo:rhyegacillos/agents-app:environment:healthcare-prod`

Current managed policies attached in the live setup:

- `AmazonEC2ContainerRegistryPowerUser`
- `AWSAppRunnerFullAccess`
- `SecretsManagerReadWrite`
- `AmazonDynamoDBFullAccess`
- `AmazonRoute53FullAccess`
- `AmazonS3FullAccess`
- `IAMReadOnlyAccess`

Current live inline policy:

- `github-actions-healthcare-iam`

Current live inline actions:

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

- bootstrap and access the Terraform backend
- create and destroy DynamoDB, ECR, App Runner, Route53, and Secrets Manager resources
- sync GitHub environment secrets into AWS Secrets Manager
- push images to ECR
- inspect App Runner deployment status

#### App Runner build role

Terraform resource:

- `aws_iam_role.apprunner_ecr_access`

Trust principal:

- `build.apprunner.amazonaws.com`

Policy attached:

- `AWSAppRunnerServicePolicyForECRAccess`

Purpose:

- allow App Runner to pull the application image from the Terraform-managed ECR repository

#### App Runner runtime role

Terraform resource:

- `aws_iam_role.apprunner_instance`

Trust principal:

- `tasks.apprunner.amazonaws.com`

Runtime permissions granted by Terraform:

- Secrets Manager:
  - `secretsmanager:GetSecretValue`
  - `secretsmanager:DescribeSecret`
- DynamoDB:
  - `dynamodb:BatchWriteItem`
  - `dynamodb:DeleteItem`
  - `dynamodb:DescribeTable`
  - `dynamodb:GetItem`
  - `dynamodb:PutItem`
  - `dynamodb:Query`
  - `dynamodb:Scan`
  - `dynamodb:UpdateItem`
- KMS:
  - `kms:Decrypt`

Runtime resource scope:

- the healthcare app secret ARNs
- the healthcare DynamoDB table ARN
- the healthcare DynamoDB table index ARNs

KMS decrypt is condition-limited to:

- `kms:ViaService = secretsmanager.${aws_region}.amazonaws.com`

### 4. Secrets Manager

Create named application secrets in AWS Secrets Manager.

Resources:

- `aws_secretsmanager_secret.openai_api_key`
- `aws_secretsmanager_secret.gemini_api_key`
- `aws_secretsmanager_secret.deepseek_api_key`
- `aws_secretsmanager_secret.grok_api_key`
- `aws_secretsmanager_secret.resend_api_key`
- `aws_secretsmanager_secret.clerk_secret_key`

If needed based on final auth setup:

- `aws_secretsmanager_secret.clerk_jwks_url`

Secret naming convention:

- `${project_name}-${environment}/app/OPENAI_API_KEY`
- `${project_name}-${environment}/app/GEMINI_API_KEY`
- `${project_name}-${environment}/app/DEEPSEEK_API_KEY`
- `${project_name}-${environment}/app/GROK_API_KEY`
- `${project_name}-${environment}/app/RESEND_API_KEY`
- `${project_name}-${environment}/app/CLERK_SECRET_KEY`

Destroy behavior:

- set `recovery_window_in_days = 0`

Reason:

- this avoids the "scheduled for deletion" name-lock problem during destroy/recreate cycles

### 5. Route53 and Custom Domain

Create and manage the custom domain through Terraform.

Resources:

- `aws_apprunner_custom_domain_association.app`
- `aws_route53_record.app_runner_custom_domain`

If `www` is needed:

- `aws_route53_record.app_runner_custom_domain_www`

Requirements:

- Route53 hosted zone name comes from a variable
- custom domain record points to App Runner `dns_target`
- Terraform owns the DNS record so destroy/recreate updates the target correctly

### 6. GitHub Actions IAM

Optionally manage GitHub Actions deploy role policy attachments similarly to `ideagen`.

Resources:

- `aws_iam_role_policy_attachment.github_actions_ecr_poweruser`
- `aws_iam_role_policy_attachment.github_actions_apprunner_fullaccess`
- `aws_iam_role_policy_attachment.github_actions_secretsmanager_readwrite`

Additional policy needed for this repo:

- DynamoDB table access for deploy-time validation or bootstrap, if required

Variable gate:

- `manage_github_actions_role_policies`
- `github_actions_role_name`

Important:

- this repo should use its own GitHub environments and its own healthcare-specific AWS deploy role
- for v1, both `healthcare-dev` and `healthcare-prod` use the same dedicated role ARN
- do not reuse `ideagen` or other repo branch roles
- the live implementation already follows this rule:
  - `healthcare-dev` -> `arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`
  - `healthcare-prod` -> `arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`
- the repository-level `AWS_ROLE_ARN` remains untouched for backward compatibility, but it is not the intended source for healthcare now

## Runtime Environment Model

### Non-secret environment variables

These should be defined directly in Terraform on the App Runner service:

- `NODE_ENV=production`
- `DYNAMODB_TABLE_NAME`
- `AWS_REGION`
- `DYNAMODB_ENDPOINT_URL` must be omitted in AWS
- `GEMINI_API_URL`
- `DEEPSEEK_API_URL`
- `GROK_API_URL`
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
- `NEXT_PUBLIC_CLERK_JWT_TEMPLATE`
- `RESEND_DOMAIN`
- `EMAIL_FROM`

### Secret environment variables

These should be injected via Secrets Manager ARN references:

- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `DEEPSEEK_API_KEY`
- `GROK_API_KEY`
- `RESEND_API_KEY`
- `CLERK_SECRET_KEY`
- possibly `CLERK_JWKS_URL` if it should be treated as secret in this repo

### Explicit AWS behavior

In AWS:

- `DYNAMODB_ENDPOINT_URL` must not be set
- the app should connect to the real DynamoDB table in the configured AWS region

Locally:

- `DYNAMODB_ENDPOINT_URL=http://localhost:8001`
- dummy AWS credentials are acceptable for DynamoDB Local

## Variables

Recommended variable set:

- `project_name`
- `environment`
- `aws_region`
- `github_repository`
- `manage_github_actions_role_policies`
- `github_actions_role_name`
- `ecr_image_tag`
- `app_runner_enabled`
- `app_runner_service_name`
- `app_runner_cpu`
- `app_runner_memory`
- `app_runner_min_size`
- `app_runner_max_size`
- `app_runner_custom_domain`
- `app_runner_enable_www_subdomain`
- `route53_hosted_zone_name`
- `dynamodb_table_name`
- `dynamodb_point_in_time_recovery_enabled`
- `dynamodb_doc_id_gsi_enabled`
- `next_public_clerk_publishable_key`
- `next_public_clerk_jwt_template`
- `gemini_api_url`
- `deepseek_api_url`
- `grok_api_url`
- `email_from`
- `resend_domain`

## Outputs

Required outputs:

- `ecr_repository_url`
- `app_runner_service_url`
- `app_runner_service_arn`
- `app_runner_ecr_access_role_arn`
- `app_runner_instance_role_arn`
- `app_runner_runtime_environment_variables`
- `app_runtime_secret_arns`
- `app_runner_custom_domain_dns_target`
- `app_runner_custom_domain_validation_records`
- `app_runner_custom_domain_status`
- `dynamodb_table_name`
- `dynamodb_table_arn`

## GitHub Actions Deployment Model

The workflow should follow the same high-level pattern as `ideagen`, with one important simplification: no RDS bootstrapping.

### CI workflow

Jobs:

- `Test`
- `Docker Build`
- `Deploy / prod`

### Deploy workflow responsibilities

1. Resolve the target environment from branch.
2. Configure AWS credentials using the branch-specific GitHub environment secret `AWS_ROLE_ARN`.
3. Validate the selected `terraform/*.tfvars`.
4. Run `terraform apply` before image push for infrastructure and config.
5. Sync runtime secrets into AWS Secrets Manager.
6. Build and push the Docker image to ECR.
7. Let App Runner auto-deploy from the new image tag.
8. Wait for App Runner to become healthy.
9. Check the health endpoint.

### Why Terraform must happen before ECR push

This keeps:

- Route53 custom domain updates
- App Runner env var updates
- App Runner secret ARN updates
- DynamoDB table references

in place before App Runner pulls the new image.

That prevents the deployment race already seen in `ideagen`.

## Destroy Behavior

Destroy must support clean rebuilds.

Requirements:

- ECR repository can be destroyed even when images exist
- Secrets Manager secrets do not remain stuck in scheduled deletion
- Route53 records are removed
- DynamoDB table is removed
- App Runner service is removed

Recommended destroy script behavior:

1. Validate tfvars path correctly when using `terraform -chdir=terraform`
2. Empty the ECR repository before destroy
3. Run `terraform destroy -var-file=<env>.tfvars`

No RDS-specific deletion protection handling is needed in this repo.

## Security Model

- Do not store secret values in Terraform variables committed to the repo.
- GitHub Actions should read secrets from GitHub environment secrets and sync values to AWS Secrets Manager during deployment.
- Restrict GitHub Actions access by both:
  - GitHub environment branch policy
  - AWS OIDC trust conditions pinned to `healthcare-dev` and `healthcare-prod`
- Keep the healthcare deploy role separate from `ideagen` and from repo-wide shared deployment roles.
- App Runner instance role should have the minimum required access:
  - `secretsmanager:GetSecretValue`
  - `secretsmanager:DescribeSecret`
  - `dynamodb:GetItem`
  - `dynamodb:PutItem`
  - `dynamodb:UpdateItem`
  - `dynamodb:Query`
  - `dynamodb:Scan`
  - `dynamodb:BatchWriteItem`

If the app code is updated to use the `doc_id` GSI explicitly, include:

- `dynamodb:Query` on the index ARN

## Operational Permission Notes

There are two different sources of permission truth in this setup:

1. Terraform code in `terraform/github_actions.tf`
2. the currently live AWS role `github-actions-healthcare-deploy`

The current live role uses:

- AWS-managed service policies for broad service access
- `IAMReadOnlyAccess`
- the inline policy `github-actions-healthcare-iam`

The optional Terraform attachments in `terraform/github_actions.tf` currently attach:

- `AmazonEC2ContainerRegistryPowerUser`
- `AWSAppRunnerFullAccess`
- `SecretsManagerReadWrite`
- `AmazonDynamoDBFullAccess`
- `AmazonRoute53FullAccess`
- `AmazonS3FullAccess`
- `IAMFullAccess`

That means the live role is slightly narrower than the optional Terraform-managed attachment set. Documentation and operations should follow the live manually created role as the source of truth unless Terraform is intentionally used to take ownership of that role configuration later.

## Known Application-Level Follow-up

The current DynamoDB store implementation still performs some wide scans:

- full scan for all documents
- full scan for `doc_id` lookup

Terraform can provision a better table shape, but the app should also be updated later to use:

- `doc_id-index` for direct lookup
- narrower query paths where possible

That is not a blocker for the initial infrastructure rollout, but it should be scheduled as a follow-up.

## Environments

Recommended initial environments:

- `dev`
- `prod`

Recommended GitHub environments:

- `healthcare-dev`
- `healthcare-prod`

Recommended role model:

- one dedicated healthcare role shared by both environments:
  - `github-actions-healthcare-deploy`

Branch mapping example:

- `healthcare-saas-aws` -> `healthcare-prod`

## Acceptance Criteria

This feature is complete when:

1. `terraform apply -var-file=prod.tfvars` creates:
   - DynamoDB table
   - ECR repository
   - App Runner service
   - Secrets Manager secret shells
   - Route53 custom domain record
2. Pushing a new image through GitHub Actions deploys successfully without manual AWS console work.
3. The deployed app uses AWS DynamoDB without `DYNAMODB_ENDPOINT_URL`.
4. The custom domain resolves to the current App Runner service after initial deploy and after destroy/recreate.
5. `terraform destroy -var-file=prod.tfvars` fully tears down the stack without blocked ECR or blocked secret names.

## Implementation Order

Recommended order:

1. Create Terraform skeleton and variables
2. Add DynamoDB table
3. Add ECR
4. Add App Runner IAM roles
5. Add App Runner service
6. Add Secrets Manager resources
7. Add Route53 custom domain resources
8. Add outputs
9. Add GitHub Actions IAM policy attachments
10. Add CI/deploy/destroy workflows
11. Test full create, deploy, and destroy cycle

## Explicit Non-Goals for V1

- Provisioning Upstash resources with Terraform
- Adding VPC, NAT gateway, or private subnets
- Adding RDS or Aurora
- Replacing the current DynamoDB application access pattern
- Multi-region disaster recovery
