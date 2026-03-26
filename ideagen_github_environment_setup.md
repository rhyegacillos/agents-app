# Ideagen GitHub Environment Setup

This document explains how to isolate GitHub Actions deployments for the `ideagen-saas-aws` branch without affecting other branches in the same repository.

The goal is:

- keep Terraform target environment as `prod`
- give this branch its own GitHub environment and AWS deploy role
- keep repo-level secrets intact
- let GitHub Actions for this branch use environment-scoped secrets instead of shared repo-wide deploy credentials

## Current Branch-Specific Setup

For the `ideagen-saas-aws` branch:

- GitHub environment: `ideagen-prod`
- allowed deployment branch: `ideagen-saas-aws`
- AWS IAM role: `github-actions-ideagen-deploy`
- AWS IAM role ARN: `arn:aws:iam::348375262167:role/github-actions-ideagen-deploy`

Important distinction:

- Terraform environment stays `prod`
- GitHub environment is `ideagen-prod`

This separation is required because the workflow needs `terraform/prod.tfvars`, but GitHub should load secrets from a branch-isolated environment.

## Why This Exists

This repository contains multiple deployment paths on different branches. Repository secrets are shared across branches by default. If a branch should deploy with different AWS permissions or different runtime secrets, repository secrets are not enough.

The proper pattern is:

- one GitHub environment per isolated deploy path
- one AWS OIDC role per isolated deploy path
- branch restrictions on the GitHub environment
- environment-scoped secrets for the deploy job

## GitHub Setup

Create a GitHub environment named `ideagen-prod`.

Add a deployment branch policy:

- branch: `ideagen-saas-aws`

Copy the ideagen deploy secrets into that environment. Do not remove the existing repository secrets unless you have explicitly migrated everything that still depends on them.

### Environment Secrets

The `ideagen-prod` environment currently expects these secrets:

- `AWS_ROLE_ARN`
- `CLERK_JWKS_URL`
- `CLERK_SECRET_KEY`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_API_URL`
- `GEMINI_API_KEY`
- `GEMINI_API_URL`
- `GROK_API_KEY`
- `GROK_API_URL`
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
- `OPENAI_API_KEY`
- `RESEND_API_KEY`

### Environment Variables

The `ideagen-prod` environment currently expects these variables:

- `AWS_ACCOUNT_ID`
- `DEFAULT_AWS_REGION`
- `NODE_ENV`
- `RESEND_DOMAIN`

Notes:

- GitHub does not allow reading back repository secret values. If a value only exists as a repo secret and is not available from a local secure source, it must be re-entered manually.
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` is public by design, but it is still safe to store at environment scope for consistency.

### Example Script To Copy Local Env Values Into A GitHub Environment

Use this pattern when you want to copy values from local `.env` files into a GitHub environment without deleting or changing repository secrets.

```bash
#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="ideagen-prod"

set -a
source ./.env
source ./.env.local
set +a

secret_keys=(
  AWS_ROLE_ARN
  CLERK_JWKS_URL
  CLERK_SECRET_KEY
  DEEPSEEK_API_KEY
  DEEPSEEK_API_URL
  EMAIL_FROM
  GEMINI_API_KEY
  GEMINI_API_URL
  GROK_API_KEY
  GROK_API_URL
  NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  OPENAI_API_KEY
  RESEND_API_KEY
)

variable_keys=(
  AWS_ACCOUNT_ID
  DEFAULT_AWS_REGION
  NODE_ENV
  RESEND_DOMAIN
)

for key in "${secret_keys[@]}"; do
  if [[ -n "${!key-}" ]]; then
    gh secret set "$key" --env "$ENV_NAME" --body "${!key}"
  fi
done

for key in "${variable_keys[@]}"; do
  if [[ -n "${!key-}" ]]; then
    gh variable set "$key" --env "$ENV_NAME" --body "${!key}"
  fi
done
```

Usage notes:

- this copies values from local files to the GitHub environment
- this does not remove repository-level secrets
- this only works for values you actually have locally
- if a secret exists only in GitHub and not in local files, GitHub must be updated manually because secret values cannot be read back

## AWS Setup

Create an IAM role named `github-actions-ideagen-deploy`.

### Trust Policy

Restrict the role to GitHub Actions jobs from this repository and GitHub environment only:

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
          "token.actions.githubusercontent.com:sub": "repo:rhyegacillos/agents-app:environment:ideagen-prod"
        }
      }
    }
  ]
}
```

### Attached Managed Policies

The branch-isolated role currently uses:

- `AmazonEC2FullAccess`
- `AmazonRDSFullAccess`
- `AmazonEC2ContainerRegistryPowerUser`
- `AWSAppRunnerFullAccess`
- `SecretsManagerReadWrite`
- `IAMReadOnlyAccess`
- `AmazonDynamoDBFullAccess`
- `AmazonS3FullAccess`
- `AmazonRoute53FullAccess`
- `AWSCertificateManagerFullAccess`

### Inline Policy

The role also needs IAM mutation rights so Terraform can manage the App Runner service roles it creates:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GitHubActionsIamRoleManagement",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole",
        "iam:DeleteRole",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:PutRolePolicy",
        "iam:DeleteRolePolicy",
        "iam:GetRole",
        "iam:GetRolePolicy",
        "iam:ListRolePolicies",
        "iam:ListAttachedRolePolicies",
        "iam:UpdateAssumeRolePolicy",
        "iam:PassRole",
        "iam:TagRole",
        "iam:UntagRole",
        "iam:ListInstanceProfilesForRole",
        "sts:GetCallerIdentity"
      ],
      "Resource": "*"
    }
  ]
}
```

After creating the role, store its ARN in the `ideagen-prod` GitHub environment as `AWS_ROLE_ARN`.

## Workflow Wiring

The workflows must not use the same value for:

- Terraform environment selection
- GitHub environment selection

Terraform still needs:

- `environment: prod`

GitHub Actions for this branch need:

- `github_environment: ideagen-prod`

Current workflow behavior:

- [ci.yml](/home/repos/ideagen-saas-aws/.github/workflows/ci.yml) calls the deploy workflow with `environment: prod` and `github_environment: ideagen-prod`
- [deploy.yml](/home/repos/ideagen-saas-aws/.github/workflows/deploy.yml) uses `github_environment` for the GitHub environment and `environment` for `TFVARS_FILE`, `DEPLOY_ENV`, and Terraform execution

This preserves:

- `terraform/prod.tfvars`
- `prod` Terraform workspace behavior
- local deploy scripts

while isolating GitHub deploy credentials and runtime secrets for this branch.

## Verification

After setup, verify:

1. `ideagen-prod` exists in GitHub
2. branch policy allows only `ideagen-saas-aws`
3. `AWS_ROLE_ARN` is present as an environment secret
4. the role trust policy references `environment:ideagen-prod`
5. a push on `ideagen-saas-aws` shows the deploy job running under `ideagen-prod`
6. the deploy job can assume `github-actions-ideagen-deploy`

## What This Does Not Change

This setup does not:

- change local Terraform deployment flow
- remove repository secrets
- modify other branches
- require renaming `terraform/prod.tfvars`

It only isolates GitHub Actions deploy credentials and environment-scoped secrets for the `ideagen-saas-aws` branch.
