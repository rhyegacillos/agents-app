# GitHub Actions Deployment Guide (Deep Dive, CI/CD)

This guide is a detailed, self-contained runbook for deploying and destroying
this app using GitHub Actions. It matches the repo workflows and scripts.

-------------------------------------------------------------------------------

## 0) Quick start

- Push to `digital-assistant-terraform` to deploy dev automatically.
- Use Actions -> "Deploy Digital Assistant" for manual deploys.
- Use Actions -> "Destroy Environment" to delete environments.

If you want full control and understanding, read the full guide below.

-------------------------------------------------------------------------------

### 0.1 Conventions (balanced default)

- Commands are bash unless labeled PowerShell.
- Replace placeholders like `<ACCOUNT_ID>` or `<ACM_CERT_ARN>`.
- Sections are ordered from high-level to low-level detail.
- Use Quick Reference when you just need the minimal steps.

-------------------------------------------------------------------------------

## 1) What this does (scope)

GitHub Actions provides CI/CD for this repo. It runs:
- `scripts/deploy.sh` to deploy infra + frontend
- `scripts/destroy.sh` to destroy infra safely

Workflows in this repo:
- `.github/workflows/deploy.yml`
- `.github/workflows/destroy.yml`

Both workflows run on GitHub hosted runners and assume an AWS role using OIDC.
No long lived AWS keys are stored in GitHub.

-------------------------------------------------------------------------------

## 2) Why use GitHub Actions

- No local AWS credentials needed on developer laptops
- All deployments are logged and reproducible
- Easy to run dev/test/prod from a single button
- Safer destroys with confirmations

-------------------------------------------------------------------------------

## 3) When to use GitHub Actions

Use GitHub Actions when:
- you want CI/CD for shared environments
- you want a single source of truth for deploys
- you need audit logs for infra changes

Use local Terraform when:
- you are debugging or iterating quickly
- you need manual control of infrastructure

-------------------------------------------------------------------------------

## 4) How the workflows work

### 4.1 Deploy workflow (`deploy.yml`)
Triggers:
- push to `digital-assistant-terraform`
- manual `workflow_dispatch` with environment input

Steps:
1) Checkout repo
2) Configure AWS credentials using OIDC role
3) Install Python + uv
4) Install Terraform
5) Install Node
6) Run `scripts/deploy.sh <env>`
7) Read Terraform outputs
8) Invalidate CloudFront
9) Print deployment summary

### 4.2 Destroy workflow (`destroy.yml`)
Triggers:
- manual `workflow_dispatch`

Steps:
1) Validate confirmation input
2) Checkout repo
3) Configure AWS credentials using OIDC role
4) Install Terraform
5) Run `scripts/destroy.sh <env>`
6) Print completion

-------------------------------------------------------------------------------

## 5) OIDC and IAM (critical)

GitHub Actions does not use AWS access keys. It uses OIDC to assume an IAM role.
This means:
- You must create an OIDC provider in AWS for GitHub.
- You must create an IAM role that trusts GitHub.
- The role must have permissions to manage all resources.

-------------------------------------------------------------------------------

## 6) Create the GitHub OIDC provider

### 6.1 Check if it exists
```bash
aws iam list-open-id-connect-providers | grep token.actions.githubusercontent.com
```

Windows PowerShell equivalent:
```powershell
aws iam list-open-id-connect-providers | findstr token.actions.githubusercontent.com
```

### 6.2 Create it (if missing)
```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

Windows PowerShell equivalent:
```powershell
aws iam create-open-id-connect-provider `
  --url https://token.actions.githubusercontent.com `
  --client-id-list sts.amazonaws.com `
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

-------------------------------------------------------------------------------

## 7) Create the IAM role for GitHub

### 7.1 Trust policy (restrict to a repo)
Create `trust-policy.json` locally:
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

If you want to restrict to a branch:
```json
"token.actions.githubusercontent.com:sub": "repo:OWNER/REPO:ref:refs/heads/digital-assistant-terraform"
```

### 7.2 Create the role
```bash
aws iam create-role \
  --role-name github-actions-digital-assistant-deploy \
  --assume-role-policy-document file://trust-policy.json
```

Windows PowerShell equivalent:
```powershell
aws iam create-role `
  --role-name github-actions-digital-assistant-deploy `
  --assume-role-policy-document file://trust-policy.json
```

-------------------------------------------------------------------------------

## 8) Attach permissions to the role

This repo uses multiple AWS services. Attach policies or a custom policy.
The fastest path is AWS managed policies:

```bash
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AWSLambda_FullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonAPIGatewayAdministrator
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/CloudFrontFullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/IAMFullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AWSCertificateManagerFullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonRoute53FullAccess
```

Windows PowerShell equivalent:
```powershell
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AWSLambda_FullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonAPIGatewayAdministrator
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/CloudFrontFullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/IAMFullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AWSCertificateManagerFullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonRoute53FullAccess
```

If you use Bedrock:
```bash
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonBedrockFullAccess
```

Windows PowerShell equivalent:
```powershell
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonBedrockFullAccess
```

### 8.1 Least privilege policy example (optional)
If you want to reduce permissions, create a custom policy instead of using
AWS managed policies. This is a baseline example you can tighten further.

Create `github-actions-deploy-policy.json`:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lambda:*",
        "apigateway:*",
        "cloudfront:*",
        "s3:*",
        "iam:GetRole",
        "iam:CreateRole",
        "iam:DeleteRole",
        "iam:PutRolePolicy",
        "iam:DeleteRolePolicy",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:PassRole",
        "acm:*",
        "route53:*",
        "dynamodb:*",
        "sts:GetCallerIdentity"
      ],
      "Resource": "*"
    }
  ]
}
```

Attach it:
```bash
aws iam create-policy \
  --policy-name github-actions-digital-assistant-deploy \
  --policy-document file://github-actions-deploy-policy.json

aws iam attach-role-policy \
  --role-name github-actions-digital-assistant-deploy \
  --policy-arn arn:aws:iam::<ACCOUNT_ID>:policy/github-actions-digital-assistant-deploy
```

Note:
- This is still broad but more controllable than multiple managed policies.
- You can reduce permissions by scoping resources by ARN or restricting actions.

-------------------------------------------------------------------------------

### 8.2 IAM role creation (AWS Console walkthrough)

This is the UI path if you prefer AWS Console instead of CLI.

Path:
1) AWS Console -> **IAM**.
2) Left sidebar -> **Roles**.
3) Click **Create role**.

Expected screen (step 1):
- Trusted entity type: **Web identity**
- Identity provider: **token.actions.githubusercontent.com**
- Audience: **sts.amazonaws.com**
- GitHub organization/repository: `OWNER/REPO`

Click **Next**.

Expected screen (step 2 - permissions):
- Search and attach the required managed policies:
  - AWSLambda_FullAccess
  - AmazonS3FullAccess
  - AmazonAPIGatewayAdministrator
  - CloudFrontFullAccess
  - IAMFullAccess
  - AmazonDynamoDBFullAccess
  - AWSCertificateManagerFullAccess
  - AmazonRoute53FullAccess
  - AmazonBedrockFullAccess (only if using Bedrock)

Click **Next**.

Expected screen (step 3 - name):
- Role name: `github-actions-digital-assistant-deploy`
- Description: optional

Click **Create role**.

Expected result:
- Role appears in the roles list.
- Role trust policy includes GitHub OIDC provider.

### 8.3 Custom IAM policy creation (AWS Console walkthrough)

Use this if you want a least‑privilege policy instead of multiple managed
policies.

Path:
1) AWS Console -> **IAM**.
2) Left sidebar -> **Policies**.
3) Click **Create policy**.

Expected screen:
- Tabs: **Visual** and **JSON**.
- Click **JSON**.

What to do:
1) Paste your policy JSON (example below).
2) Click **Next**.
3) Policy name: `github-actions-digital-assistant-deploy`
4) Description: optional
5) Click **Create policy**.

Example policy JSON (baseline):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lambda:*",
        "apigateway:*",
        "cloudfront:*",
        "s3:*",
        "iam:GetRole",
        "iam:CreateRole",
        "iam:DeleteRole",
        "iam:PutRolePolicy",
        "iam:DeleteRolePolicy",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:PassRole",
        "acm:*",
        "route53:*",
        "dynamodb:*",
        "sts:GetCallerIdentity"
      ],
      "Resource": "*"
    }
  ]
}
```

Attach the policy to the role:
1) IAM -> Roles -> `github-actions-digital-assistant-deploy`
2) Permissions tab -> **Add permissions** -> **Attach policies**
3) Search for your policy name and attach it.

### 8.4 Trust policy editing (AWS Console walkthrough)

Use this to lock the role to a specific repo or branch after creation.

Path:
1) AWS Console -> **IAM**.
2) Left sidebar -> **Roles**.
3) Click `github-actions-digital-assistant-deploy`.
4) Open the **Trust relationships** tab.
5) Click **Edit trust policy**.

Expected screen:
- JSON editor with the current trust policy.

What to edit:
- Update the `sub` condition to scope to your repo and optionally a branch.

Example (any branch in repo):
```json
"StringLike": {
  "token.actions.githubusercontent.com:sub": "repo:OWNER/REPO:*"
}
```

Example (specific branch only):
```json
"StringLike": {
  "token.actions.githubusercontent.com:sub": "repo:OWNER/REPO:ref:refs/heads/digital-assistant-terraform"
}
```

Click **Update policy** when done.

### 8.5 Attach policies after role creation (AWS Console walkthrough)

Use this if you created the role first and want to attach policies later.

Path:
1) AWS Console -> **IAM**.
2) Left sidebar -> **Roles**.
3) Click `github-actions-digital-assistant-deploy`.
4) Go to the **Permissions** tab.
5) Click **Add permissions** -> **Attach policies**.

Expected screen:
- Policy search box and list of policies.

What to do:
- Search and select required policies (or your custom policy).
- Click **Add permissions**.

Expected result:
- Policies appear under **Permissions policies** for the role.

### 8.6 Verify OIDC provider in IAM (AWS Console walkthrough)

Use this to confirm GitHub OIDC provider exists in your account.

Path:
1) AWS Console -> **IAM**.
2) Left sidebar -> **Identity providers**.

Expected screen:
- List of providers.

What to look for:
- Provider: `token.actions.githubusercontent.com`
- Type: **OpenID Connect**

If missing:
- Create it using the CLI command in Section 6.2 or the AWS Console.

### 8.7 Validate permissions with IAM Policy Simulator (AWS Console walkthrough)

Use this to confirm the GitHub Actions role can perform required actions
before running a workflow.

Path:
1) AWS Console -> **IAM**.
2) Left sidebar -> **Roles**.
3) Click `github-actions-digital-assistant-deploy`.
4) On the role summary page, click **Policy Simulator** (right side).

Expected screen:
- A simulator page with the role already selected.
- A list of services and actions to test.

What to test (minimum set):
- Service: **S3**
  - Actions: `s3:CreateBucket`, `s3:PutObject`, `s3:ListBucket`
- Service: **Lambda**
  - Actions: `lambda:CreateFunction`, `lambda:UpdateFunctionCode`
- Service: **ECR**
  - Actions: `ecr:DescribeRepositories`, `ecr:CreateRepository`, `ecr:PutLifecyclePolicy`,
    `ecr:SetRepositoryPolicy`, `ecr:GetAuthorizationToken`, `ecr:BatchGetImage`,
    `ecr:GetDownloadUrlForLayer`, `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`,
    `ecr:CompleteLayerUpload`, `ecr:PutImage`, `ecr:ListImages`
- Service: **API Gateway**
  - Actions: `apigateway:POST`, `apigateway:GET`
- Service: **CloudFront**
  - Actions: `cloudfront:CreateDistribution`, `cloudfront:GetDistribution`
- Service: **IAM**
  - Actions: `iam:CreateRole`, `iam:PassRole`, `iam:AttachRolePolicy`
- Service: **ACM**
  - Actions: `acm:RequestCertificate`, `acm:DescribeCertificate`
- Service: **Route53**
  - Actions: `route53:ListHostedZones`, `route53:ChangeResourceRecordSets`
- Service: **DynamoDB**
  - Actions: `dynamodb:CreateTable`, `dynamodb:DescribeTable`

How to run:
1) Add the services and actions above.
2) Click **Run Simulation**.

Expected result:
- All actions show **Allowed**.
- If any show **Denied**, update the role policies before running workflows.

### 8.8 Troubleshooting Policy Simulator Denied results

Use this table to map a denied action to the missing policy or permission.

| Denied action | Likely missing policy | Fix |
|---|---|---|
| `s3:CreateBucket`, `s3:PutObject` | AmazonS3FullAccess | Attach AmazonS3FullAccess or add S3 permissions in custom policy |
| `lambda:CreateFunction` | AWSLambda_FullAccess | Attach AWSLambda_FullAccess or add Lambda permissions |
| `ecr:DescribeRepositories` | AmazonEC2ContainerRegistryPowerUser | Attach AmazonEC2ContainerRegistryPowerUser or add ECR permissions |
| `apigateway:POST` | AmazonAPIGatewayAdministrator | Attach AmazonAPIGatewayAdministrator |
| `cloudfront:CreateDistribution` | CloudFrontFullAccess | Attach CloudFrontFullAccess |
| `iam:CreateRole`, `iam:PassRole` | IAMFullAccess | Attach IAMFullAccess or add specific IAM actions |
| `acm:RequestCertificate` | AWSCertificateManagerFullAccess | Attach AWSCertificateManagerFullAccess |
| `route53:ChangeResourceRecordSets` | AmazonRoute53FullAccess | Attach AmazonRoute53FullAccess |
| `dynamodb:CreateTable` | AmazonDynamoDBFullAccess | Attach AmazonDynamoDBFullAccess |

If you are using a custom least‑privilege policy, ensure the exact action
names are included in the `Action` list, or widen the resource scope.

### 8.8.1 One-time Fix for CI: Attach ECR Policy via Terraform (Local Apply)

If your workflow fails with an error like:
`AccessDeniedException: ... not authorized to perform: ecr:DescribeRepositories ...`

You can attach the required ECR managed policy to the existing GitHub Actions role via Terraform.

Run locally (with IAM admin permissions):

```bash
cd terraform
terraform workspace select dev
terraform apply \
  -var-file=terraform.tfvars \
  -var-file=terraform.tfvars.local \
  -var='manage_github_actions_role_policies=true' \
  -var='github_actions_role_name=github-actions-digital-assistant-deploy'
```

This attaches `AmazonEC2ContainerRegistryPowerUser` so CI can read/create ECR repos and push images.

### 8.9 Minimal policy snippets (non-redundant, add only what is missing)

Use these as single‑purpose statements to add to your custom policy JSON
when a specific action is denied. These are intentionally minimal.

#### S3 (create bucket + put/list objects)
```json
{
  "Effect": "Allow",
  "Action": ["s3:CreateBucket", "s3:PutObject", "s3:ListBucket"],
  "Resource": "*"
}
```

#### Lambda (create + update)
```json
{
  "Effect": "Allow",
  "Action": ["lambda:CreateFunction", "lambda:UpdateFunctionCode"],
  "Resource": "*"
}
```

#### ECR (build + push image)
```json
{
  "Effect": "Allow",
  "Action": [
    "ecr:DescribeRepositories",
    "ecr:CreateRepository",
    "ecr:PutLifecyclePolicy",
    "ecr:SetRepositoryPolicy",
    "ecr:GetAuthorizationToken",
    "ecr:BatchGetImage",
    "ecr:GetDownloadUrlForLayer",
    "ecr:InitiateLayerUpload",
    "ecr:UploadLayerPart",
    "ecr:CompleteLayerUpload",
    "ecr:PutImage",
    "ecr:ListImages"
  ],
  "Resource": "*"
}
```
#### API Gateway (create + read)
```json
{
  "Effect": "Allow",
  "Action": ["apigateway:POST", "apigateway:GET"],
  "Resource": "*"
}
```

#### CloudFront (create + read)
```json
{
  "Effect": "Allow",
  "Action": ["cloudfront:CreateDistribution", "cloudfront:GetDistribution"],
  "Resource": "*"
}
```

#### IAM (role lifecycle + pass role)
```json
{
  "Effect": "Allow",
  "Action": ["iam:CreateRole", "iam:PassRole", "iam:AttachRolePolicy"],
  "Resource": "*"
}
```

#### ACM (request + describe)
```json
{
  "Effect": "Allow",
  "Action": ["acm:RequestCertificate", "acm:DescribeCertificate"],
  "Resource": "*"
}
```

#### Route53 (list + change records)
```json
{
  "Effect": "Allow",
  "Action": ["route53:ListHostedZones", "route53:ChangeResourceRecordSets"],
  "Resource": "*"
}
```

#### DynamoDB (create + describe)
```json
{
  "Effect": "Allow",
  "Action": ["dynamodb:CreateTable", "dynamodb:DescribeTable"],
  "Resource": "*"
}
```

## 9) GitHub repo configuration (Secrets and Variables)

Open GitHub:
Settings -> Secrets and variables -> Actions

### 9.1 Required secrets
Secrets are encrypted and never shown in logs.

- `AWS_ROLE_ARN`
  - Role assumed by Actions
  - Example: arn:aws:iam::<ACCOUNT_ID>:role/github-actions-digital-assistant-deploy

- `AWS_ACCOUNT_ID`
  - Your AWS account id (12 digits)

- `DEFAULT_AWS_REGION`
  - Region used for resources (example: ap-southeast-1)

- `GROK_API_KEY`
  - Your Grok API key (required if using Grok)

- `GROK_API_URL`
  - Default: https://api.x.ai/v1

- `GROK_MODEL_ID`
  - Example: grok-4-1-fast

- `BEDROCK_MODEL_ID`
  - Example: arn:aws:bedrock:ap-southeast-1:<ACCOUNT_ID>:inference-profile/apac.amazon.nova-lite-v1:0

- `AI_PROVIDER`
  - "grok" or "bedrock"

- `ASYNC_CHAT_ENABLED`
  - "true" or "false" to enable async queue + worker

- `BRAVE_API_KEY`
  - Brave Search API key (for web search tool)

- `RESEND_API_KEY`
  - Resend API key (for email tool)

- `UPSTASH_REDIS_REST_URL`
  - Upstash Redis REST URL (required when async enabled)

- `UPSTASH_REDIS_REST_TOKEN`
  - Upstash Redis REST token (required when async enabled)

These are passed as TF_VAR_ env vars to Terraform.

### 9.2 Optional variables (repo variables)
Variables are plain text and not secret.

- `PROJECT_NAME`
  - Maps to APP_NAME in scripts (default: digital-assistant)

- `TF_BACKEND_BUCKET`
  - Overrides backend bucket name

- `TF_BACKEND_DDB_TABLE`
  - Overrides backend lock table name

If you do not set these, scripts derive them automatically.

-------------------------------------------------------------------------------

### 9.3 UI walkthroughs (no screenshots, exact clicks and expected screens)

This section gives the exact UI navigation and what you should see on each
screen, since screenshots are not included.

#### 9.3.1 GitHub Secrets and Variables

Path:
1) Open your repo on GitHub.
2) Click **Settings** (top tab).
3) In left sidebar, click **Secrets and variables** -> **Actions**.

Expected screen:
- Tabs for **Secrets** and **Variables**.
- Button **New repository secret**.
- Button **New repository variable**.

Add secrets:
1) Click **New repository secret**.
2) Name: `AWS_ROLE_ARN` -> Value: `arn:aws:iam::<ACCOUNT_ID>:role/github-actions-digital-assistant-deploy`
3) Repeat for:
   - `AWS_ACCOUNT_ID`
   - `DEFAULT_AWS_REGION`
   - `GROK_API_KEY`
   - `GROK_API_URL`
   - `GROK_MODEL_ID`
   - `BEDROCK_MODEL_ID`
   - `AI_PROVIDER`
   - `BRAVE_API_KEY`
   - `RESEND_API_KEY`
   - `UPSTASH_REDIS_REST_URL`
   - `UPSTASH_REDIS_REST_TOKEN`

Expected result:
- Secret list shows each name (values are hidden).

Add variables:
1) Click **Variables** tab.
2) Click **New repository variable**.
3) Add `PROJECT_NAME` (optional).
4) Add `TF_BACKEND_BUCKET` (optional).
5) Add `TF_BACKEND_DDB_TABLE` (optional).

Expected result:
- Variable list shows each name and value.

#### 9.3.2 GitHub Actions run (manual deploy)

Path:
1) Click **Actions** tab in repo.
2) Left sidebar: select **Deploy Digital Assistant**.
3) Click **Run workflow**.
4) Choose environment (dev/test/prod).
5) Click **Run workflow** button in the modal.

Expected screen:
- A workflow run appears in the list.
- Click it to open live logs.

Expected logs:
- "Configure AWS credentials"
- "Run Deployment Script"
- "Deployment Summary"

#### 9.3.3 GitHub Actions run (destroy)

Path:
1) Click **Actions** tab in repo.
2) Left sidebar: select **Destroy Environment**.
3) Click **Run workflow**.
4) Choose environment and type the same string in confirm.
5) Click **Run workflow**.

Expected screen:
- A workflow run appears in the list.
- Logs show confirmation and destroy progress.

-------------------------------------------------------------------------------

## 10) Deploy with GitHub Actions

### 10.1 Auto deploy on push
By default, `deploy.yml` runs on push to:
- `digital-assistant-terraform`

To change this branch, edit:
```yaml
on:
  push:
    branches: [your-branch]
```

### 10.2 Manual deploy (recommended for prod)
1) Go to GitHub -> Actions -> Deploy Digital Assistant
2) Click "Run workflow"
3) Choose environment: dev, test, or prod
4) Run

The workflow will:
- assume your OIDC role
- run scripts/deploy.sh <env>
- print the CloudFront + API URLs

Notes:
- The backend is deployed as a **container image** to Lambda (ECR-backed).
- A **worker Lambda** is deployed for async jobs when `async_chat_enabled=true`.

-------------------------------------------------------------------------------

## 11) Destroy with GitHub Actions

1) Go to GitHub -> Actions -> Destroy Environment
2) Choose environment to destroy
3) Type the environment name to confirm
4) Run

The workflow validates the confirmation before destruction.

-------------------------------------------------------------------------------

## 12) How the scripts receive configuration in CI

The workflows export environment variables before running scripts.
Key mappings:

- `AWS_ACCOUNT_ID` -> used for backend bucket naming
- `DEFAULT_AWS_REGION` -> used for backend + resources
- `APP_NAME` -> used as project_name (default: digital-assistant)
- `TF_BACKEND_BUCKET` -> overrides backend bucket name
- `TF_BACKEND_DDB_TABLE` -> overrides backend lock table
- `TF_VAR_*` -> passed directly to Terraform variables

In deploy.yml:
```yaml
TF_VAR_grok_api_key: ${{ secrets.GROK_API_KEY }}
TF_VAR_grok_api_url: ${{ secrets.GROK_API_URL }}
TF_VAR_grok_model_id: ${{ secrets.GROK_MODEL_ID }}
TF_VAR_bedrock_model_id: ${{ secrets.BEDROCK_MODEL_ID }}
TF_VAR_ai_provider: ${{ secrets.AI_PROVIDER }}
TF_VAR_brave_api_key: ${{ secrets.BRAVE_API_KEY }}
TF_VAR_resend_api_key: ${{ secrets.RESEND_API_KEY }}
TF_VAR_upstash_redis_rest_url: ${{ secrets.UPSTASH_REDIS_REST_URL }}
TF_VAR_upstash_redis_rest_token: ${{ secrets.UPSTASH_REDIS_REST_TOKEN }}
TF_VAR_async_chat_enabled: ${{ secrets.ASYNC_CHAT_ENABLED }}
TF_VAR_daily_token_limit: ${{ secrets.DAILY_TOKEN_LIMIT }}
TF_VAR_app_timezone: ${{ secrets.APP_TIMEZONE }} # e.g., Asia/Manila
TF_VAR_otel_enabled: ${{ secrets.OTEL_ENABLED }}
TF_VAR_otel_exporter_otlp_endpoint: ${{ secrets.OTEL_EXPORTER_OTLP_ENDPOINT }}
TF_VAR_otel_exporter_otlp_headers: ${{ secrets.OTEL_EXPORTER_OTLP_HEADERS }}
TF_VAR_otel_traces_sample_rate: ${{ secrets.OTEL_TRACES_SAMPLE_RATE }}
TF_VAR_otel_logs_enabled: ${{ secrets.OTEL_LOGS_ENABLED }}
TF_VAR_otel_exporter_otlp_logs_endpoint: ${{ secrets.OTEL_EXPORTER_OTLP_LOGS_ENDPOINT }}
TF_VAR_otel_exporter_otlp_logs_headers: ${{ secrets.OTEL_EXPORTER_OTLP_LOGS_HEADERS }}
TF_VAR_otel_logs_min_level: ${{ secrets.OTEL_LOGS_MIN_LEVEL }}
```

This means Terraform sees those values without any local tfvars file.

-------------------------------------------------------------------------------

## 13) Verification after a deploy

### 13.1 Check workflow logs
In the Actions run, look for:
- "Deployment complete"
- Frontend URL (custom domain or CloudFront)
- API URL (`api_custom_domain_url` when enabled, otherwise `api_gateway_url`)

### 13.2 Verify from terminal
```bash
curl -s <api_custom_domain_url>/health   # preferred when enabled
curl -s <api_gateway_url>/health         # fallback
```

### 13.3 Verify frontend
Open custom frontend domain if enabled, otherwise the CloudFront URL.

-------------------------------------------------------------------------------

## 14) Common failure modes and fixes

### 14.1 AssumeRoleWithWebIdentity not authorized
Cause:
- Trust policy does not match repo or branch
- OIDC provider missing
Fix:
- Verify trust policy `sub` matches your repo
- Verify OIDC provider exists

### 14.2 AccessDenied for ACM or Route53
Cause:
- IAM role missing permissions
Fix:
- Attach AWSCertificateManagerFullAccess
- Attach AmazonRoute53FullAccess

### 14.3 AccessDenied for DynamoDB
Cause:
- IAM role missing DynamoDB permissions
Fix:
- Attach AmazonDynamoDBFullAccess

### 14.4 Terraform backend errors
Symptoms:
- backend configuration changed
- wrong region for bucket
Fix:
- Ensure `DEFAULT_AWS_REGION` matches the bucket region
- Reconfigure backend or set TF_BACKEND_BUCKET/TF_BACKEND_DDB_TABLE

### 14.5 Missing terraform.tfvars.local
Cause:
- Workflow does not use local tfvars files
Fix:
- Provide required vars via GitHub Secrets (TF_VAR_*)

-------------------------------------------------------------------------------

## 15) Security notes

- OIDC avoids storing long lived AWS keys in GitHub.
- Limit trust policy to a single repo and branch if possible.
- Use GitHub environments for prod with required reviewers.

-------------------------------------------------------------------------------

## 16) Summary checklist

- [ ] OIDC provider created in AWS
- [ ] IAM role created and trusted for repo
- [ ] Role has required permissions
- [ ] GitHub secrets configured
- [ ] Deploy workflow runs successfully
- [ ] Destroy workflow works with confirmation

-------------------------------------------------------------------------------

## 17) Rollback / safe re-deploy (GitHub Actions)

Use these options when a workflow fails or you need to re-run safely.

### 17.1 Safe re-deploy (no destroy)
Use when the deploy failed due to transient AWS errors.
1) Open Actions -> **Deploy Digital Assistant**
2) Click **Run workflow**
3) Select the same environment and run again

### 17.2 Refresh-only (state sync)
GitHub Actions does not run refresh-only by default. If you need a refresh:
- Run `./scripts/destroy.sh <env>` locally with refresh-only step enabled, or
- Add a temporary workflow step that runs `terraform apply -refresh-only`.

### 17.3 Full rollback (destroy + redeploy)
Use when state is inconsistent or you need a clean rebuild.
1) Actions -> **Destroy Environment** (confirm environment)
2) Wait for completion
3) Actions -> **Deploy Digital Assistant** for the same environment

### 17.4 When to use each option
- Safe re-deploy: transient failures or timeouts
- Refresh-only: manual deletions or drift
- Full rollback: repeated failures or corrupted state

-------------------------------------------------------------------------------

## 18) Decision tree (text-only)

Use this quick guide to choose the safest action:

1) Did the workflow fail due to a timeout or temporary AWS error?
   - Yes -> Re-run Deploy (safe re-deploy).
   - No -> Continue.

2) Did you manually delete or modify AWS resources outside Terraform?
   - Yes -> Run refresh-only (local) or add a one-time refresh step.
   - No -> Continue.

3) Are repeated deploys failing with the same error?
   - Yes -> Destroy + redeploy (full rollback).
   - No -> Re-run Deploy.

-------------------------------------------------------------------------------

## 19) Quick reference (most common paths)

### 19.1 Deploy dev (manual)
1) Actions -> **Deploy Digital Assistant**
2) Run workflow -> environment = `dev`

### 19.2 Deploy prod (manual)
1) Actions -> **Deploy Digital Assistant**
2) Run workflow -> environment = `prod`

### 19.3 Destroy dev
1) Actions -> **Destroy Environment**
2) environment = `dev`
3) confirm = `dev`

### 19.4 Destroy prod
1) Actions -> **Destroy Environment**
2) environment = `prod`
3) confirm = `prod`

### 19.5 Safe re-deploy after failure
1) Re-run the failed Deploy workflow
2) Verify logs show CloudFront + API URLs

-------------------------------------------------------------------------------

## 20) Command cheat sheet (one-page, PowerShell)

These are the minimal PowerShell commands used in this guide.

```powershell
# Check OIDC provider
aws iam list-open-id-connect-providers | findstr token.actions.githubusercontent.com

# Create OIDC provider
aws iam create-open-id-connect-provider `
  --url https://token.actions.githubusercontent.com `
  --client-id-list sts.amazonaws.com `
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1

# Create role
aws iam create-role `
  --role-name github-actions-digital-assistant-deploy `
  --assume-role-policy-document file://trust-policy.json

# Attach managed policies
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AWSLambda_FullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonAPIGatewayAdministrator
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/CloudFrontFullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/IAMFullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AWSCertificateManagerFullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonRoute53FullAccess

# Attach Bedrock policy (if needed)
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonBedrockFullAccess
```

-------------------------------------------------------------------------------

## 21) Command cheat sheet (one-page, bash)

These are the minimal bash commands used in this guide.

```bash
# Check OIDC provider
aws iam list-open-id-connect-providers | grep token.actions.githubusercontent.com

# Create OIDC provider
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1

# Create role
aws iam create-role \
  --role-name github-actions-digital-assistant-deploy \
  --assume-role-policy-document file://trust-policy.json

# Attach managed policies
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AWSLambda_FullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonAPIGatewayAdministrator
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/CloudFrontFullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/IAMFullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AWSCertificateManagerFullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonRoute53FullAccess

# Attach Bedrock policy (if needed)
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonBedrockFullAccess
```

-------------------------------------------------------------------------------

## 22) Deployment checklists (appendix)

### 22.1 Pre-deploy checklist
- [ ] OIDC provider exists in AWS
- [ ] IAM role trust policy matches repo and branch
- [ ] Role permissions include all required services
- [ ] GitHub secrets and variables are set

### 22.2 Deploy checklist
- [ ] Run Actions -> Deploy Digital Assistant
- [ ] Confirm workflow completes without errors
- [ ] Verify CloudFront and API URLs in logs

### 22.3 Post-deploy checklist
- [ ] Open frontend URL (custom domain or CloudFront) in browser
- [ ] API `/health` returns 200
- [ ] Chat request succeeds

### 22.4 Destroy checklist
- [ ] Run Actions -> Destroy Environment
- [ ] Confirm environment string matches
- [ ] Verify resources are removed in AWS

-------------------------------------------------------------------------------

## 23) PowerShell command index (all major commands)

This appendix provides PowerShell equivalents for every important command in
this guide. Use it if you prefer Windows native shells.

### 23.1 Check OIDC provider
```powershell
aws iam list-open-id-connect-providers | findstr token.actions.githubusercontent.com
```

### 23.2 Create OIDC provider
```powershell
aws iam create-open-id-connect-provider `
  --url https://token.actions.githubusercontent.com `
  --client-id-list sts.amazonaws.com `
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

### 23.3 Create role
```powershell
aws iam create-role `
  --role-name github-actions-digital-assistant-deploy `
  --assume-role-policy-document file://trust-policy.json
```

### 23.4 Attach managed policies
```powershell
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AWSLambda_FullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonAPIGatewayAdministrator
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/CloudFrontFullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/IAMFullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AWSCertificateManagerFullAccess
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonRoute53FullAccess
```

### 23.5 Attach Bedrock policy (if needed)
```powershell
aws iam attach-role-policy --role-name github-actions-digital-assistant-deploy --policy-arn arn:aws:iam::aws:policy/AmazonBedrockFullAccess
```

### 23.6 Create custom policy (least privilege)
```powershell
aws iam create-policy `
  --policy-name github-actions-digital-assistant-deploy `
  --policy-document file://github-actions-deploy-policy.json

aws iam attach-role-policy `
  --role-name github-actions-digital-assistant-deploy `
  --policy-arn arn:aws:iam::<ACCOUNT_ID>:policy/github-actions-digital-assistant-deploy
```
