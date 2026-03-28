# Healthcare GitHub Environment Setup Runbook

This runbook explains the current GitHub Actions environment model for `healthcare-saas-aws`, how it relates to Terraform, which AWS IAM role it uses, which secrets and variables belong where, and how to recreate or repair the setup without guessing.

This document is intentionally detailed. It is the operational reference for the healthcare deployment path.

## 1. Why this repo uses GitHub environments at all

This repository shares a GitHub repository with other deployment paths. That means repository-level secrets alone are not a strong enough isolation boundary.

If only repo-level secrets were used, then:

- different branches could assume the same role unintentionally
- a deployment path could read a secret intended for another app
- workflow changes on one branch could accidentally use the wrong AWS identity

The healthcare deployment path therefore uses GitHub environments as the controlling boundary for:

- AWS OIDC role assumption
- environment-scoped application secrets
- branch restrictions for deployment jobs

## 2. Two different meanings of “environment”

This repo uses two environment systems and they are intentionally not the same thing.

### 2.1 Terraform environments

Terraform uses:

- `dev`
- `prod`

These map to:

- `terraform/dev.tfvars`
- `terraform/prod.tfvars`
- Terraform workspaces `dev` and `prod`
- remote state keys under:
  - `medinotes/dev/terraform.tfstate`
  - `medinotes/prod/terraform.tfstate`

### 2.2 GitHub environments

GitHub Actions uses:

- `healthcare-dev`
- `healthcare-prod`

These are not Terraform inputs. They are GitHub deployment-security containers that supply:

- `AWS_ROLE_ARN`
- model/provider secrets
- Clerk secrets
- Upstash secrets
- other environment-scoped config values

### 2.3 Why the split exists

Terraform needs stable infra names like `dev` and `prod`. GitHub needs branch-isolated secrets and IAM role trust restrictions. The names remain separate so each system can do its own job cleanly.

## 3. Current branch and workflow model

The current workflow implementation is:

- [ci.yml](/home/repos/healthcare-saas-aws/.github/workflows/ci.yml)
- [deploy.yml](/home/repos/healthcare-saas-aws/.github/workflows/deploy.yml)
- [destroy.yml](/home/repos/healthcare-saas-aws/.github/workflows/destroy.yml)

### 3.1 Current automatic deploy behavior

Current automatic deployment behavior is intentionally **prod-only on push**.

- push to branch `healthcare-saas-aws`
  - runs `Test`
  - runs `Docker Build`
  - runs `Deploy / prod`
  - uses GitHub environment `healthcare-prod`
  - targets Terraform environment `prod`

### 3.2 Current manual behavior

Manual `workflow_dispatch` deploy still supports:

- `dev`
- `prod`

Manual destroy also supports:

- `dev`
- `prod`

and maps to the matching GitHub environment:

- `dev` -> `healthcare-dev`
- `prod` -> `healthcare-prod`

### 3.3 Why `dev` is not auto-deployed on push anymore

The repo previously supported a separate `dev` push path. The current design intentionally avoids that. `dev` still exists, but only as a manual deployment target. This reduces accidental branch-based infrastructure churn while keeping the environment available for controlled testing.

## 4. Current live GitHub environment state

The following GitHub environments exist:

- `healthcare-dev`
- `healthcare-prod`

The following branch restrictions are intended:

- `healthcare-dev`
  - allowed branch: `dev`
- `healthcare-prod`
  - allowed branch: `healthcare-saas-aws`

These branch restrictions matter because the AWS role trust policy is also scoped by GitHub environment. The environment is the identity boundary, not just a convenient secret bucket.

## 5. Current AWS role used by healthcare

Healthcare has its own dedicated deploy role. It does not rely on the repo-wide role as the intended long-term source.

Current live role:

- role name: `github-actions-healthcare-deploy`
- role ARN: `arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`

### 5.1 Why both healthcare environments use the same ARN

This was a deliberate design choice for healthcare:

- `healthcare-dev` uses the same role ARN
- `healthcare-prod` uses the same role ARN

This does not eliminate isolation because the trust policy still restricts assumption by GitHub environment. The same physical role can still be limited to specific GitHub environment identities.

## 6. OIDC trust model

The role is assumed through GitHub OIDC using:

- federated principal:
  - `arn:aws:iam::348375262167:oidc-provider/token.actions.githubusercontent.com`

The current trust model should allow:

- `token.actions.githubusercontent.com:aud = sts.amazonaws.com`
- `token.actions.githubusercontent.com:sub = repo:rhyegacillos/agents-app:environment:healthcare-dev`
- `token.actions.githubusercontent.com:sub = repo:rhyegacillos/agents-app:environment:healthcare-prod`

This is the important point:

- the healthcare role is not just “any workflow in the repo”
- it is specifically constrained to healthcare GitHub environments

## 7. Current permissions on the healthcare deploy role

The live role currently uses these managed policies:

- `AmazonEC2ContainerRegistryPowerUser`
- `AWSAppRunnerFullAccess`
- `SecretsManagerReadWrite`
- `AmazonDynamoDBFullAccess`
- `AmazonRoute53FullAccess`
- `AmazonS3FullAccess`
- `IAMReadOnlyAccess`

It also has an inline policy:

- `github-actions-healthcare-iam`

The inline policy covers the IAM mutation actions Terraform needs for App Runner-related roles, including actions such as:

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

### 7.1 Why these permissions are needed

The GitHub role is not just pushing Docker images. It must support the entire deployment lifecycle:

- Terraform backend access through S3 and DynamoDB
- ECR push and image management
- App Runner create/update/read operations
- Secrets Manager write during deploy
- Route53 updates for the custom domain
- IAM role creation/update/pass for App Runner runtime and ECR access roles

## 8. Secrets that belong in the GitHub environments

Each healthcare environment should hold the full set of runtime secrets and secret-like configuration required by the deploy workflow.

Current expected secrets:

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

### 8.1 Why some non-secret values still live in secrets

Some of these values are configuration rather than true secrets, for example:

- `GEMINI_API_URL`
- `DEEPSEEK_API_URL`
- `GROK_API_URL`
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`

They are still environment-scoped so that deploy configuration stays aligned with the rest of the environment material and does not drift across branches.

## 9. Variables that belong in the GitHub environments

Current expected GitHub environment variables:

- `AWS_ACCOUNT_ID`
- `DEFAULT_AWS_REGION`
- `RESEND_DOMAIN`

Typical healthcare values today:

- `AWS_ACCOUNT_ID=348375262167`
- `DEFAULT_AWS_REGION=ap-southeast-1`
- `RESEND_DOMAIN=agentairg.site`

## 10. Local source of truth for syncing GitHub environments

The repo includes:

- [sync_github_environments.sh](/home/repos/healthcare-saas-aws/tools/sync_github_environments.sh)

This script is the local automation entry point for environment setup and repair.

### 10.1 What the script loads

The script reads:

- `.env`
- `.env.local`

if present.

### 10.2 What the script creates or updates

For each pair:

- `healthcare-dev` -> branch `dev`
- `healthcare-prod` -> branch `healthcare-saas-aws`

the script:

1. ensures the GitHub environment exists
2. enables custom branch policies
3. deletes old branch-policy entries
4. writes the single intended branch policy
5. writes environment secrets with `gh secret set`
6. writes environment variables with `gh variable set`

### 10.3 What the script does not do

The script does not:

- read existing secret values back out of GitHub
- create AWS IAM roles
- validate that a secret value is semantically correct
- delete the repo-level secret copies

## 11. Per-environment local override model

Healthcare uses explicit local override keys so the shared deploy role ARN can be re-synced reliably into both GitHub environments.

Current intended local keys:

- `HEALTHCARE_DEV_AWS_ROLE_ARN=arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`
- `HEALTHCARE_PROD_AWS_ROLE_ARN=arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`

These are the source of truth for syncing `AWS_ROLE_ARN` into:

- `healthcare-dev`
- `healthcare-prod`

## 12. How the workflows consume the environments

### 12.1 CI workflow

[ci.yml](/home/repos/healthcare-saas-aws/.github/workflows/ci.yml) performs:

- Python syntax validation
- npm install
- Terraform fmt/init/validate
- Docker build validation

and then calls the reusable deploy workflow only for production push.

### 12.2 Deploy workflow

[deploy.yml](/home/repos/healthcare-saas-aws/.github/workflows/deploy.yml) does the actual deploy work.

Important behaviors:

- the workflow job is attached to the selected GitHub environment
- `aws-actions/configure-aws-credentials` reads `secrets.AWS_ROLE_ARN` from that environment
- the deploy step injects runtime values only into the deploy step, not globally across the whole job
- `scripts/deploy.sh` performs the ordered deployment procedure

### 12.3 Destroy workflow

[destroy.yml](/home/repos/healthcare-saas-aws/.github/workflows/destroy.yml) requires:

- manual dispatch
- a typed confirmation of `DESTROY`

and then uses the environment-specific `AWS_ROLE_ARN` to run `scripts/destroy.sh`.

## 13. How secret values flow during deployment

This is the full path for runtime secret propagation.

1. secret values live in the GitHub environment
2. the deploy workflow loads them into the deploy step
3. `scripts/deploy.sh` syncs them into AWS Secrets Manager
4. App Runner runtime secret references point to those Secrets Manager ARNs
5. the container receives them as environment variables at runtime

This means:

- GitHub is the operator-facing source of current deploy-time values
- Secrets Manager is the runtime source the deployed app actually reads from

## 14. Verification commands

### 14.1 Check GitHub environments

```bash
gh api repos/rhyegacillos/agents-app/environments
gh api repos/rhyegacillos/agents-app/environments/healthcare-dev/deployment-branch-policies
gh api repos/rhyegacillos/agents-app/environments/healthcare-prod/deployment-branch-policies
```

### 14.2 Check secrets and variables

```bash
gh secret list --repo rhyegacillos/agents-app --env healthcare-dev
gh secret list --repo rhyegacillos/agents-app --env healthcare-prod
gh variable list --repo rhyegacillos/agents-app --env healthcare-dev
gh variable list --repo rhyegacillos/agents-app --env healthcare-prod
```

### 14.3 Check the AWS role

```bash
aws iam get-role --role-name github-actions-healthcare-deploy
aws iam list-attached-role-policies --role-name github-actions-healthcare-deploy
aws iam list-role-policies --role-name github-actions-healthcare-deploy
```

## 15. Common failure modes

### 15.1 `AWS_ROLE_ARN` exists at repo level but not in the environment

That is not the desired healthcare setup. Healthcare should use environment-scoped `AWS_ROLE_ARN` values in `healthcare-dev` and `healthcare-prod`.

### 15.2 Deploy works locally but fails in GitHub

Common causes:

- missing environment-scoped secret
- stale `AWS_ROLE_ARN`
- branch restriction mismatch
- GitHub environment missing a required value such as Upstash or Clerk secrets

### 15.3 GitHub environment exists but branch cannot deploy

Check:

- custom branch policy is enabled
- the correct branch is the only allowed branch
- the workflow job is targeting the intended GitHub environment name

### 15.4 Secret value is present in GitHub but deployed app still uses the old value

Remember the full chain:

- GitHub environment secret
- workflow deploy step
- Secrets Manager sync
- App Runner rollout

If any of those steps did not run successfully, the deployed service may still be using the old runtime value.

## 16. Current intended operational source of truth

For healthcare today, the intended source of truth is:

- GitHub environment secrets and variables for deploy-time inputs
- AWS Secrets Manager for runtime secrets after deployment
- Terraform for infrastructure and DNS
- GitHub environment OIDC role trust for deployment identity

The repo-level shared `AWS_ROLE_ARN` secret should be treated as legacy compatibility, not as the intended healthcare configuration.

