# Deployment + Ops Runbook

This runbook describes the current production deployment path after the migration from SQLite to PostgreSQL.

It assumes:

- AWS App Runner for the app runtime
- Amazon RDS for PostgreSQL for the database
- Terraform as the infrastructure source of truth
- Secrets Manager for runtime app secrets
- Alembic for schema migrations

## 1. Runtime Topology

```text
Developer / GitHub Actions
  -> Terraform
      -> VPC + subnets + NAT
      -> RDS PostgreSQL
      -> ECR
      -> Secrets Manager
      -> App Runner + VPC connector

App Runner
  -> public HTTPS ingress
  -> private egress through VPC connector
  -> RDS in private subnets
```

## 2. Environment Model

Application database selection is controlled by:

- `APP_ENV=local|prod`
- `DATABASE_URL_LOCAL`
- `DATABASE_URL_PROD`

Current behavior in [api/config.py](/home/repos/ideagen-saas-aws/api/config.py):

- `APP_ENV=local` requires `DATABASE_URL_LOCAL`
- `APP_ENV=prod` requires `DATABASE_URL_PROD`
- default environment falls back to `prod` when AWS runtime markers are present, otherwise `local`

Infrastructure environment selection is separate from app runtime mode and is handled by Terraform env var-files:

- `terraform/dev.tfvars`
- `terraform/test.tfvars`
- `terraform/prod.tfvars`

## 3. Schema Migration Ownership

Schema creation is owned by Alembic.

Important rule:

- do not rely on ad hoc runtime table creation
- do not treat the database as valid until `alembic upgrade head` has been applied

Current container behavior:

- [scripts/start_server.sh](/home/repos/ideagen-saas-aws/scripts/start_server.sh) runs `alembic upgrade head`
- then starts `uvicorn`

Current local direct backend behavior:

- if you run `uvicorn` manually, you must run `alembic upgrade head` yourself first

## 4. Required Runtime Configuration

### Required app variables

- `APP_ENV`
- `CLERK_JWKS_URL`
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `GEMINI_API_URL`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_API_URL`
- `GROK_API_KEY`
- `GROK_API_URL`
- `RESEND_API_KEY`

### Required database variables

- `DATABASE_URL_LOCAL` when `APP_ENV=local`
- `DATABASE_URL_PROD` when `APP_ENV=prod`

### Recommended runtime variables

- `EMAIL_FROM`
- `ALLOWED_HOSTS`
- `TOKEN_LIMIT_FREE`
- `TOKEN_LIMIT_PREMIUM`
- `SAVED_RESULTS_LIMIT_FREE_BYTES`
- `SAVED_RESULTS_LIMIT_PREMIUM_BYTES`
- `DB_POOL_SIZE`
- `DB_MAX_OVERFLOW`
- `DB_POOL_TIMEOUT`
- `DB_POOL_RECYCLE`
- `DB_ECHO`

## 5. Local Development Runbook

### Step 1: Start local Postgres

```bash
docker compose up -d postgres
```

### Step 2: Configure env

Example:

```bash
APP_ENV=local
DATABASE_URL_LOCAL=postgresql+psycopg://postgres:postgres@localhost:5432/ideagen_dev
```

### Step 3: Apply migrations

```bash
alembic upgrade head
```

### Step 4: Run backend/frontend

Backend:

```bash
cd api
uvicorn index:app --reload --port 8000
```

Frontend:

```bash
npm run dev
```

## 6. Local Infrastructure Deployment

Use the environment-aware deploy wrapper:

```bash
./scripts/deploy.sh dev
./scripts/deploy.sh prod
```

### What the local deploy wrapper does

For the selected environment, [scripts/deploy.sh](/home/repos/ideagen-saas-aws/scripts/deploy.sh) calls [scripts/deploy_terraform_local.sh](/home/repos/ideagen-saas-aws/scripts/deploy_terraform_local.sh), which:

1. loads `.env`
2. bootstraps the Terraform backend bucket and lock table if needed
3. initializes Terraform with the correct remote state key
4. selects the matching Terraform workspace
5. bootstraps non-App Runner resources only on first deploy
6. syncs app secrets into Secrets Manager
7. builds and pushes the Docker image to ECR
8. applies Terraform for the App Runner resource
9. waits for rollout completion or triggers `start-deployment` if the service is already stable
10. checks `/health`

## 7. GitHub Deployment Runbook

GitHub Actions workflows:

- deploy: [.github/workflows/deploy.yml](/home/repos/ideagen-saas-aws/.github/workflows/deploy.yml)
- destroy: [.github/workflows/destroy.yml](/home/repos/ideagen-saas-aws/.github/workflows/destroy.yml)
- CI: [.github/workflows/ci.yml](/home/repos/ideagen-saas-aws/.github/workflows/ci.yml)

Deploy workflow order:

1. checkout
2. Python dependency install
3. backend tests
4. AWS credential setup
5. Terraform backend bootstrap
6. Terraform init + workspace selection
7. first-deploy bootstrap if App Runner is not already managed in state
8. sync runtime secrets to Secrets Manager
9. build and push Docker image to ECR
10. apply Terraform for App Runner
11. if App Runner is already `RUNNING`, trigger `start-deployment`
12. otherwise wait for Terraform-driven rollout to finish
13. verify `/health`

Destroy workflow:

- manual only
- explicit environment selection
- explicit `DESTROY` confirmation

## 8. RDS Operations

Production database is expected to be Amazon RDS PostgreSQL.

Operational expectations:

- DB runs in private subnets
- App Runner reaches DB through a VPC connector
- RDS master password is AWS-managed in Secrets Manager
- App runtime receives `DATABASE_URL_PROD` from app-specific Secrets Manager entries

### Backup and restore

Use Postgres-native or RDS-native workflows:

- automated snapshots
- manual snapshots before risky changes
- `pg_dump` / `pg_restore` for logical export/import

Do not rely on container filesystem state for recovery.

## 9. App Runner Custom Domain

Current canonical production domain:

- `ideagen.agentairg.site`

Custom domain association is managed by Terraform and Route 53.

Operational checks:

```bash
dig ideagen.agentairg.site +short
curl -I https://ideagen.agentairg.site
```

Expected behavior:

- domain resolves to the current App Runner default host
- App Runner custom domain status is `ACTIVE`
- app root returns `200`

## 10. Host Allowlist

The backend rejects unexpected hosts.

Current implementation in [api/index.py](/home/repos/ideagen-saas-aws/api/index.py):

- `/health` bypasses host allowlist checks
- `ALLOWED_HOSTS` supports comma-separated values
- wildcard entries such as `*.awsapprunner.com` are accepted

Recommended production setting:

```bash
ALLOWED_HOSTS=ideagen.agentairg.site,*.awsapprunner.com
```

Use the App Runner wildcard only when you intentionally want the service URL to stay reachable during rollout or debugging.

## 11. Health and Verification

### App health

```bash
curl https://<service-url>/health
```

Expected:

```json
{"status":"healthy"}
```

### Migration verification

Check application logs for:

- `Running Alembic migrations`
- `Running upgrade -> ...`
- `Starting uvicorn`

### Auth verification

If authenticated routes fail with Clerk token verification errors, verify:

- `CLERK_JWKS_URL`
- outbound DNS/network access from App Runner
- the live App Runner runtime config values

## 12. Common Failure Modes

### `relation "user_usage" does not exist`

Meaning:

- the app is connected to Postgres
- the schema has not been migrated yet

Fix:

- run `alembic upgrade head`
- or redeploy with the startup migration wrapper in place

### `Host not allowed`

Meaning:

- the request host is not in `ALLOWED_HOSTS`

Fix:

- add the production custom domain
- add `*.awsapprunner.com` temporarily if you need to validate against the App Runner service URL

### `Token verification failed: Fail to fetch data from the url`

Meaning:

- Clerk JWKS URL is wrong or unreachable

Fix:

- verify `CLERK_JWKS_URL`
- verify App Runner runtime env values

### `Can't start a deployment ... because it isn't in RUNNING state`

Meaning:

- a rollout is already in progress

Current fix already applied:

- deploy scripts now wait when Terraform has already triggered a rollout
- they only call `start-deployment` when the service is already `RUNNING`

## 13. Safe Ops Checklist

Before deploy:

- verify the correct Terraform var-file for the environment
- verify `.env` or GitHub secrets contain the intended runtime values
- ensure `ALLOWED_HOSTS` matches the target domain strategy

After deploy:

- verify App Runner status
- verify `/health`
- verify authenticated endpoint behavior such as `/api/subscription`
- verify app root on the custom domain
- scan CloudWatch application logs for migration/auth/provider failures
