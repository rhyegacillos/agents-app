# Terraform AWS Design and Implementation Status for `healthcare-saas-aws`

This document started as the design spec for the healthcare AWS rollout. It now serves two roles:

1. the design reference for why the stack was shaped the way it was
2. the implementation-status record for what is now live

It should be read as the bridge between the original plan and the current deployed reality.

## 1. Original goal

The goal of this stack was to give `healthcare-saas-aws` an AWS deployment model similar to `ideagen-saas-aws` where it matters, while intentionally avoiding infrastructure that this application does not need.

Required outcomes were:

- Terraform-managed AWS stack
- GitHub Actions deployment and destroy workflows
- App Runner deployment from ECR
- durable patient memory outside the container
- runtime secrets managed outside source control
- custom-domain ownership under Terraform
- destroy/recreate support without secret-name or ECR teardown failures

## 2. Why the healthcare stack differs from `ideagen`

`ideagen` required a private database topology. Healthcare does not.

The healthcare app currently depends on:

- DynamoDB
- Secrets Manager
- Upstash Redis
- App Runner

It does not currently require:

- RDS
- VPC
- private subnets
- NAT gateway
- App Runner VPC connector

That is why the healthcare Terraform stack intentionally focuses on:

- DynamoDB
- ECR
- App Runner
- Secrets Manager
- Route53
- IAM

without copying the full `ideagen` VPC/RDS footprint.

## 3. Design decisions that were implemented

### 3.1 Memory moved to DynamoDB

The app no longer uses a local JSON file as the deployed memory store. Long-term patient memory now uses DynamoDB only.

This was the core product-side infrastructure change because it made patient history survive redeploys and App Runner instance replacement.

### 3.2 Secrets moved to AWS Secrets Manager

Terraform now creates the secret containers and the deploy pipeline writes the values. App Runner consumes those values through runtime secret references.

This keeps secret values out of Terraform state and out of source control.

### 3.3 Route53 became Terraform-managed

The custom domain is now part of the infrastructure model rather than a manual post-deploy step. This avoids stale DNS when App Runner services are recreated or adopted.

### 3.4 GitHub environments became part of the deployment identity model

The repo now uses:

- `healthcare-dev`
- `healthcare-prod`

with a dedicated healthcare deploy role and environment-scoped `AWS_ROLE_ARN`.

### 3.5 Destroy was hardened

Destroy now accounts for the AWS failure modes encountered during implementation:

- ECR repositories must be emptied before deletion
- Secrets Manager names must be immediately reusable
- Terraform state backend and workspace handling must be consistent

## 4. Current implementation status

### 4.1 Implemented in code

The following are implemented in the repository:

- Terraform stack under `terraform/`
- deploy script under `scripts/deploy.sh`
- destroy script under `scripts/destroy.sh`
- GitHub Actions workflows under `.github/workflows/`
- GitHub environment sync tooling under `tools/sync_github_environments.sh`
- DynamoDB-only memory backend in application code
- DynamoDB Local support for local development

### 4.2 Implemented in AWS/GitHub

The following are no longer just planned; they are provisioned or configured:

- GitHub environments:
  - `healthcare-dev`
  - `healthcare-prod`
- branch restrictions:
  - `healthcare-dev` -> `dev`
  - `healthcare-prod` -> `healthcare-saas-aws`
- dedicated AWS role:
  - `arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`
- environment-scoped `AWS_ROLE_ARN` in both healthcare GitHub environments
- production App Runner service under Terraform ownership
- production ECR repository under Terraform ownership
- production custom-domain route under Terraform ownership
- production DynamoDB table active for patient memory
- production deploy workflow verified working

### 4.3 Adopted production resources

Production was not built from a blank slate. The implementation intentionally adopted existing live resources into Terraform state where appropriate.

Current adopted production names:

- App Runner service:
  - `consultation-app-service`
- ECR repository:
  - `consultation-app`
- custom domain:
  - `medinotes.agentairg.site`
- DynamoDB table:
  - `medinotes-prod-memory`

This is why the production tfvars include explicit name overrides instead of relying only on generated defaults.

## 5. Current AWS resource model

### 5.1 DynamoDB

Implemented:

- `aws_dynamodb_table.memory`

Current design:

- `PAY_PER_REQUEST`
- hash key `pk`
- range key `sk`
- `doc_id-index` GSI

Role in the system:

- persistent patient memory storage
- patient-history retrieval
- assistant historical recall
- evidence/note/summary durability across deploys

### 5.2 ECR

Implemented:

- `aws_ecr_repository.app`
- `aws_ecr_lifecycle_policy.app`

Current design:

- mutable tags
- lifecycle cleanup
- `force_delete = true`
- scan on push enabled

### 5.3 App Runner

Implemented:

- `aws_apprunner_service.app`
- `aws_apprunner_auto_scaling_configuration_version.main`
- `aws_apprunner_custom_domain_association.app`

Current design:

- ECR-backed image source
- auto deployments enabled
- runtime secrets resolved from Secrets Manager ARNs
- non-secret runtime config provided as environment variables
- public service, no VPC connector

### 5.4 Secrets Manager

Implemented:

- secret shells for all runtime secrets

Current design:

- Terraform creates the secret resources
- deploy tooling writes the actual secret values
- `recovery_window_in_days = 0`

### 5.5 Route53

Implemented:

- custom-domain record in Terraform

Current design:

- Route53 record points at the App Runner custom-domain target
- DNS drift from destroy/recreate is no longer acceptable as a manual process

## 6. Current IAM design

### 6.1 GitHub Actions deploy role

Live role:

- `github-actions-healthcare-deploy`
- `arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`

Used by:

- `healthcare-dev`
- `healthcare-prod`

Trust restrictions:

- GitHub OIDC only
- audience `sts.amazonaws.com`
- `sub` limited to:
  - `repo:rhyegacillos/agents-app:environment:healthcare-dev`
  - `repo:rhyegacillos/agents-app:environment:healthcare-prod`

Current live managed policies:

- `AmazonEC2ContainerRegistryPowerUser`
- `AWSAppRunnerFullAccess`
- `SecretsManagerReadWrite`
- `AmazonDynamoDBFullAccess`
- `AmazonRoute53FullAccess`
- `AmazonS3FullAccess`
- `IAMReadOnlyAccess`

Current live inline policy:

- `github-actions-healthcare-iam`

### 6.2 App Runner roles

Terraform also creates:

- App Runner ECR access role
- App Runner runtime role

Their responsibilities are separate from the GitHub role:

- build role pulls from ECR
- runtime role reads Secrets Manager and accesses DynamoDB

## 7. Current GitHub Actions design

### 7.1 CI workflow

The CI workflow now validates:

- Python syntax
- npm dependency installation
- Terraform fmt
- Terraform init without backend
- Terraform validate
- Docker build viability

### 7.2 Automatic deploy behavior

Current automatic deploy behavior:

- push to `healthcare-saas-aws` -> deploy `prod`

`dev` remains available as a manual target rather than an automatic push target.

### 7.3 Deploy-order design

The deploy order is now:

1. initialize backend and workspace
2. apply infrastructure and service configuration
3. sync runtime secrets into Secrets Manager
4. build and push the image
5. let App Runner auto-deploy the pushed image
6. wait for healthy service state

This ordering was chosen specifically to avoid deployment races and stale-config rollouts.

## 8. Problems the implementation explicitly solved

The following issues came up during implementation and are now part of the intended design:

### 8.1 Manual App Runner adoption

The production App Runner service already existed. Terraform support was adjusted so the stack could adopt and manage that existing service rather than requiring a destructive rebuild.

### 8.2 Secret-name reuse after destroy

Secrets Manager names blocked redeploys after destroy until `recovery_window_in_days = 0` was applied to secret resources.

### 8.3 ECR teardown failures

Destroy failed on non-empty ECR repositories until the destroy path was hardened to empty the repository before Terraform destroy.

### 8.4 Route53 drift after service recreation

The custom domain kept pointing at old App Runner targets until the Route53 record became Terraform-managed.

### 8.5 Patient memory loss across deploys

The original local-file memory model was not acceptable for App Runner. Moving memory to DynamoDB was the key fix that made patient history durable.

## 9. Current remaining non-blocking gaps

The foundational stack is in place, but some areas remain evolutionary rather than final:

- DynamoDB search is still application-scored rather than using a managed vector service
- some IAM permissions could be narrowed further if needed
- the DynamoDB Terraform resource still emits a provider deprecation warning about `hash_key`
- `dev` exists operationally but is not part of the normal automatic push path

These are not blockers for the current deployment model.

## 10. Design conclusions

The healthcare stack now has the important properties the original plan called for:

- persistent patient memory outside the container
- secret values managed outside Terraform state
- reproducible AWS infrastructure
- Terraform-managed custom domain
- GitHub environment-based deployment identity
- working deploy and destroy paths
- local DynamoDB simulation without changing the AWS runtime model

In practice, this means `healthcare-saas-aws` is no longer “an App Runner app with a few manual settings.” It is now an infrastructure-managed application platform with clear ownership boundaries across Terraform, GitHub Actions, Secrets Manager, and DynamoDB.

