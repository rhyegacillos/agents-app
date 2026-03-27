# Healthcare GitHub Environment Setup Runbook

This document is the full reference for how `healthcare-saas-aws` is isolated in GitHub Actions and how to recreate or repair that setup.

It covers:

- why separate GitHub environments are required
- the exact GitHub environments and branch policies used
- which local values are copied into GitHub
- how the sync script works internally
- the dedicated AWS role used by healthcare
- how the workflows consume the environments
- how to verify and troubleshoot the setup

This is not just a summary. It is the operational runbook for this repo.

## 1. Deployment model

This repo uses two different concepts of “environment”:

### Terraform environment

Terraform uses:

- `dev`
- `prod`

These map to:

- `terraform/dev.tfvars`
- `terraform/prod.tfvars`
- Terraform workspaces `dev` and `prod`
- remote state keys:
  - `medinotes/dev/terraform.tfstate`
  - `medinotes/prod/terraform.tfstate`

### GitHub Actions environment

GitHub Actions uses:

- `healthcare-dev`
- `healthcare-prod`

These are branch-isolated secret containers for GitHub jobs.

### Why both exist

The workflows need Terraform to keep using `dev` and `prod`, but GitHub needs branch-isolated deploy credentials and secrets.

So the separation is:

- Terraform target: `dev` or `prod`
- GitHub environment: `healthcare-dev` or `healthcare-prod`

## 2. Current intended mapping

### Branch to GitHub environment

- branch `dev` -> GitHub environment `healthcare-dev`
- branch `healthcare-saas-aws` -> GitHub environment `healthcare-prod`

### Branch to Terraform environment

- branch `dev` -> Terraform `dev`
- branch `healthcare-saas-aws` -> Terraform `prod`

### Current workflow wiring

This is implemented in:

- [ci.yml](/home/repos/healthcare-saas-aws/.github/workflows/ci.yml)
- [deploy.yml](/home/repos/healthcare-saas-aws/.github/workflows/deploy.yml)
- [destroy.yml](/home/repos/healthcare-saas-aws/.github/workflows/destroy.yml)

Behavior:

- push to `dev` triggers `Deploy / dev` with GitHub environment `healthcare-dev`
- push to `healthcare-saas-aws` triggers `Deploy / prod` with GitHub environment `healthcare-prod`
- manual destroy selects `healthcare-dev` or `healthcare-prod` based on the destroy target

## 3. Why repository secrets are not enough

This repository shares a single GitHub repo with other deployment paths. Repository secrets are shared across branches by default.

That creates two problems:

1. one branch can accidentally deploy with another branch’s AWS role
2. one branch can accidentally deploy with another branch’s runtime secrets

The correct pattern is:

- one GitHub environment per deployment path
- one AWS IAM role per deployment path
- branch restrictions on each GitHub environment
- environment-scoped secrets used by the deploy and destroy workflows

## 4. Current live GitHub environment state

The following environments have already been created in GitHub:

- `healthcare-dev`
- `healthcare-prod`

The following deployment branch policies have already been applied:

- `healthcare-dev` allows only branch `dev`
- `healthcare-prod` allows only branch `healthcare-saas-aws`

This was applied by [sync_github_environments.sh](/home/repos/healthcare-saas-aws/tools/sync_github_environments.sh).

The following dedicated AWS role now exists for healthcare:

- role name: `github-actions-healthcare-deploy`
- role ARN: `arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`

This healthcare-specific role is used by both:

- `healthcare-dev`
- `healthcare-prod`

That is intentional because both healthcare environments currently deploy the same AWS stack shape and share the same AWS account/resources model.

The repository-level `AWS_ROLE_ARN` secret was left untouched. Healthcare is no longer intended to depend on that repo-wide secret. The intended source for healthcare is now the environment-scoped `AWS_ROLE_ARN` in:

- `healthcare-dev`
- `healthcare-prod`

## 5. Required GitHub environment secrets

Each environment is expected to contain these secrets:

- `AWS_ROLE_ARN`
- `BRAVE_API_KEY`
- `CLERK_JWKS_URL`
- `CLERK_SECRET_KEY`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_API_URL`
- `GEMINI_API_KEY`
- `GEMINI_API_URL`
- `GROK_API_KEY`
- `GROK_API_URL`
- `NEXT_PUBLIC_CLERK_JWT_TEMPLATE`
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
- `OPENAI_API_KEY`
- `RESEND_API_KEY`
- `RESEND_FROM`
- `UPSTASH_REDIS_REST_TOKEN`
- `UPSTASH_REDIS_REST_URL`

Notes:

- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` is public by design, but it is still stored at environment scope for consistency.
- `RESEND_FROM` falls back in the workflow to `MediNotes <no-reply@agentairg.site>` if not present, but it should still be set explicitly.
- `DEEPSEEK_API_URL`, `GEMINI_API_URL`, and `GROK_API_URL` are treated as secrets in the workflow, even though they are configuration values.

## 6. Required GitHub environment variables

Each environment is expected to contain these variables:

- `AWS_ACCOUNT_ID`
- `DEFAULT_AWS_REGION`
- `RESEND_DOMAIN`

Current local values that were copied:

- `AWS_ACCOUNT_ID=348375262167`
- `DEFAULT_AWS_REGION=ap-southeast-1`
- `RESEND_DOMAIN=agentairg.site`

## 7. What was copied automatically

The sync process already copied all locally available values from:

- `.env`
- `.env.local`

into:

- `healthcare-dev`
- `healthcare-prod`

The healthcare-specific AWS role ARN is now also stored locally through environment-specific override keys:

- `HEALTHCARE_DEV_AWS_ROLE_ARN=arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`
- `HEALTHCARE_PROD_AWS_ROLE_ARN=arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`

Those override keys are the intended source of truth for syncing `AWS_ROLE_ARN` into GitHub for healthcare.

## 8. Sync script reference

The environment automation lives in:

- [sync_github_environments.sh](/home/repos/healthcare-saas-aws/tools/sync_github_environments.sh)

### What the script does

For each of these pairs:

- `healthcare-dev : dev`
- `healthcare-prod : healthcare-saas-aws`

the script performs:

1. loads `.env` if present
2. loads `.env.local` if present
3. creates or updates the GitHub environment
4. enables custom branch policies for that environment
5. deletes any existing branch policy entries on that environment
6. creates the single expected branch policy
7. writes matching secrets into the environment using `gh secret set`
8. writes matching variables into the environment using `gh variable set`

### What the script does not do

The script does not:

- read back existing GitHub secret values
- create AWS IAM roles
- verify that the values are correct for production
- remove repository-level secrets

### Script source of truth

The script uses these arrays internally:

#### Secrets copied

- `AWS_ROLE_ARN`
- `BRAVE_API_KEY`
- `CLERK_JWKS_URL`
- `CLERK_SECRET_KEY`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_API_URL`
- `GEMINI_API_KEY`
- `GEMINI_API_URL`
- `GROK_API_KEY`
- `GROK_API_URL`
- `NEXT_PUBLIC_CLERK_JWT_TEMPLATE`
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
- `OPENAI_API_KEY`
- `RESEND_API_KEY`
- `RESEND_FROM`
- `UPSTASH_REDIS_REST_TOKEN`
- `UPSTASH_REDIS_REST_URL`

#### Variables copied

- `AWS_ACCOUNT_ID`
- `DEFAULT_AWS_REGION`
- `RESEND_DOMAIN`

### Default behavior in the script

If `RESEND_FROM` is missing locally, the script uses:

- `MediNotes <no-reply@agentairg.site>`

### Per-environment overrides

If a value should be different for `healthcare-dev` and `healthcare-prod`, export an override before running the script.

Naming format:

- `HEALTHCARE_DEV_<KEY>`
- `HEALTHCARE_PROD_<KEY>`

Examples:

```bash
export HEALTHCARE_DEV_AWS_ROLE_ARN="arn:aws:iam::348375262167:role/github-actions-healthcare-deploy"
export HEALTHCARE_PROD_AWS_ROLE_ARN="arn:aws:iam::348375262167:role/github-actions-healthcare-deploy"

export HEALTHCARE_DEV_RESEND_FROM="MediNotes Dev <no-reply@agentairg.site>"
export HEALTHCARE_PROD_RESEND_FROM="MediNotes <no-reply@agentairg.site>"

cd /home/repos/healthcare-saas-aws
./tools/sync_github_environments.sh
```

Override precedence is:

1. `HEALTHCARE_<ENV>_<KEY>`
2. plain env var loaded from `.env` or `.env.local`
3. `RESEND_FROM` fallback only

## 9. Exact setup process from scratch

If you need to recreate the setup from zero, use this process.

### Step 1. Authenticate GitHub CLI

Verify:

```bash
gh auth status
```

Required scopes:

- `repo`
- `workflow`

### Step 2. Ensure local env files are present

At least one of these should exist:

- `.env`
- `.env.local`

They should contain the app values you want to copy.

### Step 3. Export per-environment overrides if needed

Use this especially for:

- `AWS_ROLE_ARN`
- any value that differs between dev and prod

Example:

```bash
export HEALTHCARE_DEV_AWS_ROLE_ARN="arn:aws:iam::348375262167:role/github-actions-healthcare-deploy"
export HEALTHCARE_PROD_AWS_ROLE_ARN="arn:aws:iam::348375262167:role/github-actions-healthcare-deploy"
```

### Step 4. Run the sync script

```bash
cd /home/repos/healthcare-saas-aws
./tools/sync_github_environments.sh
```

### Step 5. Verify GitHub environments

List environments:

```bash
gh api repos/rhyegacillos/agents-app/environments
```

Check dev branch policy:

```bash
gh api repos/rhyegacillos/agents-app/environments/healthcare-dev/deployment-branch-policies
```

Check prod branch policy:

```bash
gh api repos/rhyegacillos/agents-app/environments/healthcare-prod/deployment-branch-policies
```

Check environment secrets:

```bash
gh secret list --repo rhyegacillos/agents-app --env healthcare-dev
gh secret list --repo rhyegacillos/agents-app --env healthcare-prod
```

Check environment variables:

```bash
gh variable list --repo rhyegacillos/agents-app --env healthcare-dev
gh variable list --repo rhyegacillos/agents-app --env healthcare-prod
```

## 10. AWS IAM role setup

The script does not create AWS IAM roles. Those must exist already.

Current live role:

- `github-actions-healthcare-deploy`

Current GitHub environment secret mapping:

- `AWS_ROLE_ARN` in `healthcare-dev` -> `arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`
- `AWS_ROLE_ARN` in `healthcare-prod` -> `arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`

### Trust policy pattern

The healthcare role should be restricted to the healthcare GitHub environments only.

Allowed OIDC subjects:

- `repo:rhyegacillos/agents-app:environment:healthcare-dev`
- `repo:rhyegacillos/agents-app:environment:healthcare-prod`

The exact OIDC provider used by the role is:

- `arn:aws:iam::348375262167:oidc-provider/token.actions.githubusercontent.com`

The exact audience restriction used by the role is:

- `token.actions.githubusercontent.com:aud = sts.amazonaws.com`

### Current trust policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::348375262167:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": [
            "repo:rhyegacillos/agents-app:environment:healthcare-dev",
            "repo:rhyegacillos/agents-app:environment:healthcare-prod"
          ]
        }
      }
    }
  ]
}
```

### Current live role metadata

The current AWS role metadata is:

- role name: `github-actions-healthcare-deploy`
- role ARN: `arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`
- path: `/`
- description: `GitHub Actions deploy role for healthcare-saas-aws`
- max session duration: `3600`

### Current attached managed policies

The current live healthcare role has these AWS-managed policies attached:

- `AmazonEC2ContainerRegistryPowerUser`
  - required for ECR login, image push, tag operations, and repository management during deploy/destroy
- `AWSAppRunnerFullAccess`
  - required for App Runner service create, update, describe, custom-domain association, and deployment status checks
- `SecretsManagerReadWrite`
  - required because the workflow syncs GitHub environment secrets into AWS Secrets Manager before deployment
- `AmazonDynamoDBFullAccess`
  - required for Terraform-managed DynamoDB table create, update, describe, and destroy
- `AmazonRoute53FullAccess`
  - required for custom-domain DNS record creation and updates in `agentairg.site`
- `AmazonS3FullAccess`
  - required for Terraform remote state bucket bootstrap and access
- `IAMReadOnlyAccess`
  - required for read-only IAM inspection during Terraform role lifecycle operations

### Current inline policy

The current live healthcare role also has an inline policy:

- policy name: `github-actions-healthcare-iam`

This inline policy grants the mutation permissions that `IAMReadOnlyAccess` does not provide.

Current action set:

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

This inline policy is currently scoped to:

- `Resource = "*"`

That broad resource scope matches the current Terraform pattern used for creating and updating the App Runner IAM roles. If the IAM scope is tightened later, it must still allow the workflow and Terraform to manage:

- `${project_name}-${environment}-apprunner-ecr-access`
- `${project_name}-${environment}-apprunner-instance`

### Why the role is shaped this way

The role must be able to support this stack:

- Terraform backend bootstrap:
  - S3
  - DynamoDB
- Terraform-managed infra:
  - DynamoDB
  - ECR
  - App Runner
  - Secrets Manager
  - Route53
  - IAM role creation for App Runner runtime/build roles

That is why the live role uses:

- broad service-level managed policies for AWS services
- read-only managed access for IAM inspection
- a narrow inline IAM mutation policy for Terraform-managed role creation and updates

This is the same operational pattern that was used in `ideagen`, adapted for the healthcare stack.

## 11. Terraform-managed IAM roles inside the stack

Separate from the GitHub Actions deploy role, Terraform creates App Runner service roles inside the target healthcare stack.

These are not GitHub roles. They are runtime roles used by App Runner itself.

### App Runner ECR access role

Terraform resource:

- [main.tf](/home/repos/healthcare-saas-aws/terraform/main.tf) `aws_iam_role.apprunner_ecr_access`

Role name pattern:

- `${project_name}-${environment}-apprunner-ecr-access`

Assumed by:

- `build.apprunner.amazonaws.com`

Attached managed policy:

- `service-role/AWSAppRunnerServicePolicyForECRAccess`

Purpose:

- let App Runner pull the container image from the managed ECR repository

### App Runner instance role

Terraform resource:

- [main.tf](/home/repos/healthcare-saas-aws/terraform/main.tf) `aws_iam_role.apprunner_instance`

Role name pattern:

- `${project_name}-${environment}-apprunner-instance`

Assumed by:

- `tasks.apprunner.amazonaws.com`

Inline runtime policy:

- [main.tf](/home/repos/healthcare-saas-aws/terraform/main.tf) `aws_iam_role_policy.apprunner_instance_runtime`

Granted secret access:

- `secretsmanager:GetSecretValue`
- `secretsmanager:DescribeSecret`

Granted DynamoDB access:

- `dynamodb:BatchWriteItem`
- `dynamodb:DeleteItem`
- `dynamodb:DescribeTable`
- `dynamodb:GetItem`
- `dynamodb:PutItem`
- `dynamodb:Query`
- `dynamodb:Scan`
- `dynamodb:UpdateItem`

Granted KMS access:

- `kms:Decrypt`

KMS decrypt is condition-limited to:

- `kms:ViaService = secretsmanager.${aws_region}.amazonaws.com`

The role is scoped to the Terraform-created healthcare resources:

- the healthcare Secrets Manager secret ARNs
- the healthcare DynamoDB table ARN
- the healthcare DynamoDB index ARNs

This is the runtime permission model for the app itself. GitHub Actions does not use this role directly.

## 12. How workflows consume these environments

### CI entrypoint

[ci.yml](/home/repos/healthcare-saas-aws/.github/workflows/ci.yml) does the branch routing:

- `dev` branch -> reusable deploy workflow with:
  - `environment: dev`
  - `github_environment: healthcare-dev`
- `healthcare-saas-aws` branch -> reusable deploy workflow with:
  - `environment: prod`
  - `github_environment: healthcare-prod`

### Deploy workflow

[deploy.yml](/home/repos/healthcare-saas-aws/.github/workflows/deploy.yml) uses:

- `inputs.environment` for:
  - `TFVARS_FILE`
  - `TFVARS_NAME`
  - `DEPLOY_ENV`
  - workspace selection
- `inputs.github_environment` for:
  - GitHub environment-scoped secrets

This workflow expects:

- `AWS_ROLE_ARN` in the selected GitHub environment
- all runtime secrets in the selected GitHub environment

It then:

1. validates tfvars
2. assumes the environment-specific AWS role
3. bootstraps the Terraform backend
4. selects the Terraform workspace
5. bootstraps infra on first deploy
6. syncs runtime secrets into AWS Secrets Manager
7. pushes the image to ECR
8. creates or rolls App Runner
9. waits for `/health`

### Destroy workflow

[destroy.yml](/home/repos/healthcare-saas-aws/.github/workflows/destroy.yml) picks the GitHub environment based on the requested target:

- destroy `dev` -> `healthcare-dev`
- destroy `prod` -> `healthcare-prod`

So destroy also depends on the correct `AWS_ROLE_ARN` in both GitHub environments.

## 13. Exact verification commands

These commands verify the live GitHub and AWS role state.

### Verify GitHub environments

```bash
gh api repos/rhyegacillos/agents-app/environments
gh api repos/rhyegacillos/agents-app/environments/healthcare-dev/deployment-branch-policies
gh api repos/rhyegacillos/agents-app/environments/healthcare-prod/deployment-branch-policies
gh secret list --repo rhyegacillos/agents-app --env healthcare-dev
gh secret list --repo rhyegacillos/agents-app --env healthcare-prod
gh variable list --repo rhyegacillos/agents-app --env healthcare-dev
gh variable list --repo rhyegacillos/agents-app --env healthcare-prod
```

### Verify the healthcare deploy role

```bash
aws iam get-role --role-name github-actions-healthcare-deploy
aws iam list-attached-role-policies --role-name github-actions-healthcare-deploy
aws iam list-role-policies --role-name github-actions-healthcare-deploy
aws iam get-role-policy --role-name github-actions-healthcare-deploy --policy-name github-actions-healthcare-iam
```

### Verify the local override source of truth

```bash
grep '^HEALTHCARE_DEV_AWS_ROLE_ARN=' .env
grep '^HEALTHCARE_PROD_AWS_ROLE_ARN=' .env
```

## 14. Verification checklist

Use this after any environment update.

### GitHub checks

1. `healthcare-dev` exists
2. `healthcare-prod` exists
3. `healthcare-dev` has only `dev` as deployment branch policy
4. `healthcare-prod` has only `healthcare-saas-aws` as deployment branch policy
5. both environments contain `AWS_ROLE_ARN`
6. both environments contain the expected secrets and variables

### Workflow checks

1. push a test commit to `dev`
2. confirm `Deploy / dev` runs under `healthcare-dev`
3. push a test commit to `healthcare-saas-aws`
4. confirm `Deploy / prod` runs under `healthcare-prod`
5. confirm `configure-aws-credentials` succeeds in both environments

### AWS checks

1. the assumed role in the workflow matches the environment-specific role
2. the workflow can bootstrap the Terraform state bucket and lock table
3. the workflow can write application secrets to Secrets Manager
4. the workflow can push to ECR
5. the workflow can create or update App Runner

## 13. Troubleshooting

### Problem: `AWS_ROLE_ARN` missing

Symptom:

- `configure-aws-credentials` fails immediately

Fix:

- set `HEALTHCARE_DEV_AWS_ROLE_ARN`
- set `HEALTHCARE_PROD_AWS_ROLE_ARN`
- rerun:

```bash
./tools/sync_github_environments.sh
```

or enter `AWS_ROLE_ARN` manually in the GitHub UI for both environments

### Problem: script says “Skipped secret … (no local value)”

Meaning:

- the key was not present in `.env`
- and not present in `.env.local`
- and no per-environment override was exported

Fix:

- add the value locally or export an override, then rerun the script

### Problem: branch policy becomes wrong

Meaning:

- someone changed the GitHub environment manually

Fix:

- rerun:

```bash
./tools/sync_github_environments.sh
```

The script deletes existing deployment branch policies for the managed environments and recreates the expected single policy.

### Problem: GitHub API transient failure during sync

Meaning:

- network or GitHub API issue interrupted the run

Fix:

- rerun the script

The script is idempotent:

- environments are updated in place
- branch policy is reset to the expected value
- secrets and variables are overwritten with the same values

## 14. What this setup does not change

This setup does not:

- remove repository-level secrets
- migrate repo-level secrets automatically
- read back GitHub secret values
- create the AWS IAM roles for you
- change local DynamoDB behavior
- provision Upstash resources

It only isolates GitHub Actions deployment configuration for this app.

## 15. Current state

The healthcare GitHub environment setup is now fully defined as:

- dedicated AWS role: `github-actions-healthcare-deploy`
- dedicated ARN used in both healthcare environments:
  - `arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`
- local override keys:
  - `HEALTHCARE_DEV_AWS_ROLE_ARN`
  - `HEALTHCARE_PROD_AWS_ROLE_ARN`

If you rerun:

```bash
cd /home/repos/healthcare-saas-aws
./tools/sync_github_environments.sh
```

the script should keep both healthcare GitHub environments pinned to that dedicated healthcare role.
