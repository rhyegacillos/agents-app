# GitHub Actions Deployment Guide

This document is the current runbook for deploying and destroying the app from
GitHub Actions. It reflects the repo as it exists now, including:

- one main CI workflow in [ci.yml](/home/repos/twin/.github/workflows/ci.yml)
- one destroy workflow in [destroy.yml](/home/repos/twin/.github/workflows/destroy.yml)
- Bedrock as the deploy-time provider default
- runtime secrets stored in AWS Secrets Manager instead of Terraform-managed
  Lambda environment variables
- `prod` as the default deployment target for CI pushes and manual dispatches

-------------------------------------------------------------------------------

## 0) Quick start

- Push to `digital-assistant-terraform` to run CI and deploy to `prod` by
  default.
- Use Actions -> `CI` -> `Run workflow` if you want to deploy `dev`, `test`, or
  `prod` manually.
- Use Actions -> `Destroy Environment` to destroy a specific environment.

Current workflows:
- [.github/workflows/ci.yml](/home/repos/twin/.github/workflows/ci.yml)
- [.github/workflows/destroy.yml](/home/repos/twin/.github/workflows/destroy.yml)

-------------------------------------------------------------------------------

## 1) What the CI workflow actually does

The CI workflow is no longer split into separate `deploy.yml` and
`docs-consistency.yml` files. The current graph is:

1. `Test`
2. `Docker Build`
3. `deploy`

`deploy` waits for both `Test` and `Docker Build`.

### 1.1 `Test` job

The `Test` job runs on GitHub-hosted Ubuntu and does:

1. checkout
2. Python 3.12 setup
3. `uv` install
4. Node 20 setup
5. backend dependency install with `uv sync`
6. frontend dependency install with `npm ci`
7. architecture facts check:
   `python scripts/render_architecture_facts.py --check`
8. backend unit tests:
   `cd backend && uv run python -m unittest discover -s tests -p "test_*.py"`
9. frontend lint:
   `cd frontend && npm run lint`

### 1.2 `Docker Build` job

This job is only a build smoke test. It does not push an image.

It runs:

```bash
docker build \
  --platform linux/amd64 \
  --provenance=false \
  --sbom=false \
  -t digital-assistant-ci:${GITHUB_SHA} \
  ./backend
```

The `--provenance=false` and `--sbom=false` flags matter because Lambda image
compatibility is stricter than a generic OCI consumer.

### 1.3 `deploy` job

The deploy job performs the real rollout:

1. checkout
2. assume the AWS OIDC deploy role
3. Python setup
4. `uv` install
5. Terraform setup
6. Node setup
7. resolve the environment-specific runtime secret ARN
8. sync runtime secret values into AWS Secrets Manager
9. run [deploy.sh](/home/repos/twin/scripts/deploy.sh)
10. read Terraform outputs
11. run the golden-set E2E evals
12. upload eval results
13. invalidate CloudFront
14. print deployment summary

-------------------------------------------------------------------------------

## 2) Deployment target selection

### 2.1 Current default

The current default deployment target is `prod`.

In [ci.yml](/home/repos/twin/.github/workflows/ci.yml):

- `workflow_dispatch.inputs.environment.default` is `prod`
- `deploy.environment` defaults to `prod`
- `DEPLOY_ENV` defaults to `prod`

This means:

- a push to `digital-assistant-terraform` deploys `prod`
- a manual workflow run also defaults to `prod` unless you override it

### 2.2 Manual override

You can still deploy another environment manually:

1. Open Actions -> `CI`
2. Click `Run workflow`
3. Choose `dev`, `test`, or `prod`

The workflow will then bind the job to the matching GitHub Environment and use
the matching runtime secret ARN.

-------------------------------------------------------------------------------

## 3) Runtime secret model

This repo no longer passes raw runtime API keys into Terraform.

That change was made specifically to avoid leaking runtime secrets into:

- Terraform state
- Lambda environment variables managed by Terraform
- GitHub Actions logs via broad variable forwarding

### 3.1 What is stored in Secrets Manager

The runtime secret payload is a JSON document with keys such as:

- `GROK_API_KEY`
- `BRAVE_API_KEY`
- `RESEND_API_KEY`
- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`
- `OTEL_EXPORTER_OTLP_HEADERS`
- `OTEL_EXPORTER_OTLP_LOGS_HEADERS`

### 3.2 What Lambda receives

Terraform now passes only:

- `APP_RUNTIME_SECRETS_ARN`

The backend resolves actual secrets at runtime through
[secret_env.py](/home/repos/twin/backend/secret_env.py).

### 3.3 Current secret naming convention

The script [runtime_secret.sh](/home/repos/twin/scripts/runtime_secret.sh)
uses this logical name when no explicit ARN is supplied:

```text
<project_name>/<environment>/runtime
```

Current concrete examples in AWS:

- `digital-assistant/dev/runtime`
- `digital-assistant/prod/runtime`

### 3.4 Environment-scoped runtime secret variables in GitHub

The workflow now resolves the runtime secret ARN from environment-specific repo
variables before it calls `runtime_secret.sh`.

Current variables:

- `DEV_RUNTIME_SECRETS_ARN`
- `TEST_RUNTIME_SECRETS_ARN`
- `PROD_RUNTIME_SECRETS_ARN`
- `RUNTIME_SECRETS_ARN`

Resolution order in [ci.yml](/home/repos/twin/.github/workflows/ci.yml):

1. if `DEPLOY_ENV=dev`, use `DEV_RUNTIME_SECRETS_ARN`
2. if `DEPLOY_ENV=test`, use `TEST_RUNTIME_SECRETS_ARN`
3. if `DEPLOY_ENV=prod`, use `PROD_RUNTIME_SECRETS_ARN`
4. if the env-specific value is empty, fall back to `RUNTIME_SECRETS_ARN`

The workflow then passes that ARN to the sync step as `RUNTIME_SECRETS_ARN`.

### 3.5 Why the workflow has both “resolve” and “sync” behavior

The deploy job performs two distinct tasks:

1. choose which secret ARN belongs to the target environment
2. update the secret value contents before deploy

That means the secret can be precreated once, while the current GitHub secrets
still overwrite the stored JSON payload during each deploy.

-------------------------------------------------------------------------------

## 4) GitHub configuration required

### 4.1 Repository secrets

These secrets are expected by the workflow:

- `AWS_ROLE_ARN`
- `AWS_ACCOUNT_ID`
- `DEFAULT_AWS_REGION`
- `GROK_API_URL`
- `GROK_MODEL_ID`
- `GROK_API_KEY`
- `BRAVE_API_KEY`
- `RESEND_API_KEY`
- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`
- `OTEL_EXPORTER_OTLP_HEADERS` (optional)
- `OTEL_EXPORTER_OTLP_LOGS_HEADERS` (optional)

### 4.2 Repository variables

These variables are expected or supported:

- `PROJECT_NAME`
- `TF_BACKEND_BUCKET`
- `TF_BACKEND_DDB_TABLE`
- `BEDROCK_MODEL_ID`
- `ASYNC_CHAT_ENABLED`
- `DEV_RUNTIME_SECRETS_ARN`
- `TEST_RUNTIME_SECRETS_ARN`
- `PROD_RUNTIME_SECRETS_ARN`
- `RUNTIME_SECRETS_ARN` as a fallback only

### 4.3 GitHub Environments

The repo already has environment records for:

- `dev`
- `prod`

The deploy job binds to:

```yaml
environment: ${{ github.event.inputs.environment || 'prod' }}
```

That means environment protection rules, reviewers, and environment-scoped
secrets can be layered later if needed.

-------------------------------------------------------------------------------

## 5) AWS OIDC role requirements

### 5.1 Trust policy

The GitHub role must trust the GitHub Actions OIDC provider and allow the repo
to assume it.

The repo currently uses the role:

```text
github-actions-digital-assistant-deploy
```

The trust policy can be repo-wide:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:OWNER/REPO:*"
        }
      }
    }
  ]
}
```

If you want to restrict to this deployment branch only:

```json
"token.actions.githubusercontent.com:sub": "repo:OWNER/REPO:ref:refs/heads/digital-assistant-terraform"
```

### 5.2 Broad AWS service permissions

The role needs enough AWS access to perform the full deployment lifecycle.

In the current account, the role is using a mix of AWS managed policies such as:

- `AWSLambda_FullAccess`
- `AmazonS3FullAccess`
- `AmazonEC2ContainerRegistryPowerUser`
- `AmazonAPIGatewayAdministrator`
- `CloudFrontFullAccess`
- `AmazonDynamoDBFullAccess`
- `AWSCertificateManagerFullAccess`
- `AmazonRoute53FullAccess`
- `AmazonBedrockFullAccess`
- `IAMReadOnlyAccess`

There are also inline policies for:

- additional IAM role management used by Terraform
- runtime secret write access

### 5.3 Runtime secret IAM permissions

The deploy role must be able to update the per-environment runtime secret.

The currently required minimum permissions are:

- `secretsmanager:DescribeSecret`
- `secretsmanager:PutSecretValue`

Current resource scope pattern:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ManageDigitalAssistantRuntimeSecrets",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:DescribeSecret",
        "secretsmanager:PutSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:ap-southeast-1:<ACCOUNT_ID>:secret:digital-assistant/*/runtime*"
    }
  ]
}
```

This is the permission set that removed the last GitHub deploy blocker.

### 5.4 Why `CreateSecret` is no longer required

Originally, deploys were trying to create the runtime secret during CI.
That failed because the GitHub role did not have `CreateSecret`.

The current design avoids that dependency by:

1. precreating env-scoped runtime secrets once
2. storing their ARNs in GitHub variables
3. having CI only update their contents with `PutSecretValue`

That is the safer model and should remain the default.

-------------------------------------------------------------------------------

## 6) Exact deploy flow in the current workflow

For a push to `digital-assistant-terraform`, the current sequence is:

1. `Test` job verifies docs consistency, backend tests, and frontend lint.
2. `Docker Build` proves the backend image can be built on GitHub runners.
3. `deploy` starts with `DEPLOY_ENV=prod`.
4. The job resolves `PROD_RUNTIME_SECRETS_ARN`.
5. `runtime_secret.sh sync prod digital-assistant` updates the AWS secret JSON.
6. `deploy.sh prod` runs.
7. `deploy.sh`:
   - selects the Terraform workspace
   - ensures ECR exists
   - builds and pushes the Lambda image
   - applies Terraform
   - updates Lambda image digests
   - builds the frontend with the current API URL
   - uploads frontend assets to S3
   - invalidates CloudFront
8. The workflow reads Terraform outputs.
9. The workflow runs the golden-set E2E evals against the deployed API.
10. The workflow uploads eval results and prints a summary.

-------------------------------------------------------------------------------

## 7) Exact destroy flow

The destroy workflow remains manual only.

Current file:
- [destroy.yml](/home/repos/twin/.github/workflows/destroy.yml)

Sequence:

1. require explicit confirmation text equal to the environment name
2. checkout
3. assume the AWS OIDC role
4. initialize Terraform
5. resolve `TF_VAR_runtime_secrets_arn`
6. run [destroy.sh](/home/repos/twin/scripts/destroy.sh)

Important detail:

- if an explicit runtime secret ARN is supplied, `runtime_secret.sh delete`
  becomes a no-op
- that means destroys do not automatically delete precreated shared runtime
  secrets, which is the intended behavior

-------------------------------------------------------------------------------

## 8) Operational notes and current caveats

### 8.1 Prod is now the default

This is intentional, but it changes the safety profile of branch pushes.

If you want human approval before production deploys, add protection rules to
the GitHub `prod` Environment instead of changing the workflow back to `dev`.

### 8.2 Node 20 deprecation warnings

Current runs still show GitHub warnings for actions that are on Node 20. Those
warnings are not failing the workflow, but they should be cleaned up before
GitHub’s Node 24 cutoff.

### 8.3 Eval failures are now distinct from deploy failures

Earlier failures were caused by:

- stale docs
- missing tracked files
- secret sync/IAM issues
- Terraform still requiring old secret vars

Those have been resolved. If CI goes red again now, it is more likely to be:

- a real infrastructure failure
- a post-deploy eval failure
- a new code regression

-------------------------------------------------------------------------------

## 9) Current source of truth

For the exact implementation, use:

- [ci.yml](/home/repos/twin/.github/workflows/ci.yml)
- [destroy.yml](/home/repos/twin/.github/workflows/destroy.yml)
- [deploy.sh](/home/repos/twin/scripts/deploy.sh)
- [destroy.sh](/home/repos/twin/scripts/destroy.sh)
- [runtime_secret.sh](/home/repos/twin/scripts/runtime_secret.sh)
- [DEPLOYMENT_TERRAFORM.md](/home/repos/twin/DEPLOYMENT_TERRAFORM.md)

This document is the GitHub-side operational guide. Terraform specifics,
including backend, workspaces, and script internals, are documented in
[DEPLOYMENT_TERRAFORM.md](/home/repos/twin/DEPLOYMENT_TERRAFORM.md).
