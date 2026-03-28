# GitHub Actions + Environment Setup Runbook

This runbook explains how GitHub Actions is configured for `healthcare-saas-aws`, how the GitHub environments are structured, how the AWS role is wired through OIDC, and how to recreate or repair the setup.

This document is deliberately detailed and operational. It is the GitHub Actions counterpart to [deployment_runbook.md](/home/repos/healthcare-saas-aws/deployment_runbook.md).

## 1. Goals of the GitHub setup

The GitHub Actions setup has four jobs:

1. validate the application and Terraform on every production push
2. deploy production automatically on push to the production branch
3. keep `dev` available for manual deployment
4. isolate deploy credentials through GitHub environments instead of relying on repo-wide secrets alone

## 2. Current workflow inventory

Current workflow files:

- [ci.yml](/home/repos/healthcare-saas-aws/.github/workflows/ci.yml)
- [deploy.yml](/home/repos/healthcare-saas-aws/.github/workflows/deploy.yml)
- [destroy.yml](/home/repos/healthcare-saas-aws/.github/workflows/destroy.yml)

## 3. Current branch behavior

### Automatic production deployment

Pushes to:

- `healthcare-saas-aws`

trigger:

- `Test`
- `Docker Build`
- `Deploy / prod`

### Manual environments

Manual workflow dispatch can still target:

- `dev`
- `prod`

That means `dev` is still operationally supported even though it is no longer an automatic push-deploy branch.

## 4. GitHub environments

Current GitHub environments:

- `healthcare-dev`
- `healthcare-prod`

### Current intended branch restrictions

- `healthcare-dev`
  - allowed branch: `dev`
- `healthcare-prod`
  - allowed branch: `healthcare-saas-aws`

These restrictions matter because the AWS trust policy is scoped by GitHub environment.

## 5. Why GitHub environments are required

Repository-level secrets alone are not the intended model because this repo is shared and hosts multiple deployment paths over time.

GitHub environments are used so that:

- deploy jobs run under an environment identity
- `AWS_ROLE_ARN` is scoped to that environment
- branch restrictions control which branch may use that environment
- runtime secrets are grouped per deployment path

## 6. Current AWS role used by the workflows

Current dedicated healthcare deploy role:

- role name: `github-actions-healthcare-deploy`
- role ARN: `arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`

Current design:

- `healthcare-dev` uses this ARN
- `healthcare-prod` also uses this ARN

That is intentional. Isolation is enforced by the OIDC trust conditions on GitHub environment identity, not by maintaining separate dev/prod role names.

## 7. OIDC trust model

The role should trust:

- federated principal:
  - `arn:aws:iam::348375262167:oidc-provider/token.actions.githubusercontent.com`

with:

- `token.actions.githubusercontent.com:aud = sts.amazonaws.com`
- `token.actions.githubusercontent.com:sub = repo:rhyegacillos/agents-app:environment:healthcare-dev`
- `token.actions.githubusercontent.com:sub = repo:rhyegacillos/agents-app:environment:healthcare-prod`

This means a workflow must run under one of those GitHub environments to assume the role.

## 8. Current permissions on the role

Managed policies currently attached:

- `AmazonEC2ContainerRegistryPowerUser`
- `AWSAppRunnerFullAccess`
- `SecretsManagerReadWrite`
- `AmazonDynamoDBFullAccess`
- `AmazonRoute53FullAccess`
- `AmazonS3FullAccess`
- `IAMReadOnlyAccess`

Inline policy currently attached:

- `github-actions-healthcare-iam`

Purpose of the inline policy:

- allow Terraform to create, update, tag, attach policies to, and pass the App Runner-related IAM roles it manages

## 9. Secrets expected in the GitHub environments

Current expected environment secrets:

- `AWS_ROLE_ARN`
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
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
- `NEXT_PUBLIC_CLERK_JWT_TEMPLATE`
- `GEMINI_API_URL`
- `DEEPSEEK_API_URL`
- `GROK_API_URL`
- `RESEND_FROM`

## 10. Variables expected in the GitHub environments

Current expected environment variables:

- `AWS_ACCOUNT_ID`
- `DEFAULT_AWS_REGION`
- `RESEND_DOMAIN`

## 11. How deploy secrets flow into production

The current deploy secret chain is:

1. GitHub environment secret
2. deploy step in GitHub Actions
3. `scripts/deploy.sh`
4. AWS Secrets Manager write
5. App Runner runtime secret reference
6. container environment variable at runtime

This is important because updating a GitHub secret does not by itself update the running application. A deploy must run so the new value is written into Secrets Manager and then picked up by the service rollout.

## 12. Workflow behavior in detail

### 12.1 `ci.yml`

Responsibilities:

- Python syntax check
- npm dependency install
- Terraform fmt
- Terraform init without backend
- Terraform validate
- Docker build validation
- call reusable deploy workflow for production push

### 12.2 `deploy.yml`

Responsibilities:

- attach the correct GitHub environment
- assume the AWS role from `AWS_ROLE_ARN`
- run `scripts/deploy.sh`

Important current implementation detail:

- secrets are scoped to the deploy step, not broadcast across every job step

### 12.3 `destroy.yml`

Responsibilities:

- require manual dispatch
- require exact `DESTROY` confirmation
- attach the matching GitHub environment
- assume the AWS role
- run `scripts/destroy.sh`

## 13. Local environment sync automation

The repo includes:

- [tools/sync_github_environments.sh](/home/repos/healthcare-saas-aws/tools/sync_github_environments.sh)

### What it does

The script:

1. loads `.env` if present
2. loads `.env.local` if present
3. creates or updates:
   - `healthcare-dev`
   - `healthcare-prod`
4. resets branch policies to the intended single-branch mapping
5. writes environment secrets with `gh secret set`
6. writes environment variables with `gh variable set`

### What it does not do

The script does not:

- create the AWS role
- read back secret values from GitHub
- validate semantic correctness of the values
- remove repo-level secrets

## 14. Local override model for `AWS_ROLE_ARN`

Healthcare uses environment-specific override keys for syncing the same dedicated role into both GitHub environments:

- `HEALTHCARE_DEV_AWS_ROLE_ARN`
- `HEALTHCARE_PROD_AWS_ROLE_ARN`

Current intended values:

- `HEALTHCARE_DEV_AWS_ROLE_ARN=arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`
- `HEALTHCARE_PROD_AWS_ROLE_ARN=arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`

This is the local source of truth for the environment-scoped `AWS_ROLE_ARN` values.

## 15. Verification commands

### Check environments and branch policies

```bash
gh api repos/rhyegacillos/agents-app/environments
gh api repos/rhyegacillos/agents-app/environments/healthcare-dev/deployment-branch-policies
gh api repos/rhyegacillos/agents-app/environments/healthcare-prod/deployment-branch-policies
```

### Check environment secrets and variables

```bash
gh secret list --repo rhyegacillos/agents-app --env healthcare-dev
gh secret list --repo rhyegacillos/agents-app --env healthcare-prod
gh variable list --repo rhyegacillos/agents-app --env healthcare-dev
gh variable list --repo rhyegacillos/agents-app --env healthcare-prod
```

### Check the AWS role

```bash
aws iam get-role --role-name github-actions-healthcare-deploy
aws iam list-attached-role-policies --role-name github-actions-healthcare-deploy
aws iam list-role-policies --role-name github-actions-healthcare-deploy
```

## 16. Common failure modes

### Deploy can’t assume the role

Check:

- `AWS_ROLE_ARN` exists in the target GitHub environment
- the workflow job is attached to the expected GitHub environment
- the OIDC trust policy includes the correct `sub`

### GitHub secret exists but app still uses the old runtime value

Check:

- did a deploy run after the GitHub secret was updated
- did `scripts/deploy.sh` successfully sync the value into Secrets Manager
- did App Runner roll out the new runtime state

### Wrong branch can’t deploy

That may be correct behavior. Check the branch policy for the GitHub environment.

### `dev` does not auto-deploy on push

That is also current intended behavior. `dev` is manual-only at the moment.

## 17. Operational source of truth

For GitHub Actions specifically, the source of truth is:

- workflow files in `.github/workflows/`
- GitHub environment configuration
- the healthcare deploy IAM role in AWS
- the local sync script for reproducing environment configuration

Use this runbook together with:

- [deployment_runbook.md](/home/repos/healthcare-saas-aws/deployment_runbook.md)
- [healthcare_github_environment_setup.md](/home/repos/healthcare-saas-aws/healthcare_github_environment_setup.md)

when you need to rebuild or audit the deployment path end to end.

