# IdeaGen

IdeaGen is a multi-model business idea generator and report engine. It helps a signed-in user move from idea exploration to execution planning:

1. generate one or more model outputs for a chosen industry, constraint set, and persona
2. optionally use a premium recommendation helper to choose a stronger persona and constraint combination before generation
3. save those outputs as durable runs
4. compare saved runs to identify a stronger direction
5. create a decision summary over one or more runs
6. generate an execution plan from saved evidence

This README is the guided walkthrough for how the system works and how to run it. The full technical explanation lives in [ARCHITECTURE.md](/home/repos/ideagen-saas-aws/ARCHITECTURE.md).

## Current Architecture

The runtime shape of the app is:

```text
Browser (Next.js static UI)
  -> FastAPI API
      -> Clerk JWT verification
      -> quota/usage checks
      -> multi-provider LLM orchestration
      -> PDF rendering (WeasyPrint)
      -> email delivery (Resend)
      -> PostgreSQL via SQLAlchemy
           -> local Postgres in development
           -> Amazon RDS PostgreSQL in AWS
```

In practice, that means one deployed service handles both the frontend and the backend. The frontend is built as static assets and served by FastAPI from the same container image that also serves API routes. The backend is the control plane of the application: it verifies the user, enforces plan and quota limits, coordinates agent modules, persists artifacts, and handles report delivery.

The product is artifact-centric, not one-shot. A generation request is usually followed by an auto-save. Later actions such as compare, decision summary, and execution plan are built from saved artifacts rather than from temporary text sitting only in browser memory.

For the full runtime explanation, see [ARCHITECTURE.md](/home/repos/ideagen-saas-aws/ARCHITECTURE.md#system-summary).

## System Walkthrough

The easiest way to understand IdeaGen is to follow one user request from the browser through the stack.

The browser first loads a static Next.js frontend. The user works in the authenticated workspace implemented in [pages/product.tsx](/home/repos/ideagen-saas-aws/pages/product.tsx). That page manages the step-by-step workflow, retrieves the Clerk token, calls the API, hydrates saved artifacts back into the UI, and triggers export or email actions. It also includes a premium-only recommendation helper that can prefill a suggested persona and constraint set before generation. The frontend is therefore not just a display layer. It actively coordinates the product workflow.

When the user performs an action, the browser calls FastAPI in [api/index.py](/home/repos/ideagen-saas-aws/api/index.py). The backend verifies the Clerk JWT, determines the user’s plan from token claims, checks quota or premium gates, validates the request, and then routes the action to the appropriate feature path. If the action needs reasoning, FastAPI invokes the relevant worker module under [api/agent](/home/repos/ideagen-saas-aws/api/agent). If the action needs durable state, it reads or writes through [api/db.py](/home/repos/ideagen-saas-aws/api/db.py), which uses SQLAlchemy models and sessions to talk to PostgreSQL.

If the result needs to be delivered as a shareable artifact, the backend renders PDFs through WeasyPrint and can send supported report types through Resend. Current email delivery covers the current idea payload, saved comparisons, and saved decision summaries; execution plans currently support PDF and presentation export, but not email delivery. If the result needs to survive beyond the current request, it is stored in PostgreSQL as a saved run, comparison, decision summary, or execution plan. In production, the same application code runs on App Runner, reads secrets from environment variables injected via Secrets Manager, and reaches RDS PostgreSQL through a VPC connector.

For the deeper walkthrough of frontend orchestration, backend orchestration, persistence, and infrastructure, see:

- [ARCHITECTURE.md](/home/repos/ideagen-saas-aws/ARCHITECTURE.md#frontend-architecture)
- [ARCHITECTURE.md](/home/repos/ideagen-saas-aws/ARCHITECTURE.md#backend-architecture)
- [ARCHITECTURE.md](/home/repos/ideagen-saas-aws/ARCHITECTURE.md#persistence-architecture)
- [ARCHITECTURE.md](/home/repos/ideagen-saas-aws/ARCHITECTURE.md#deployment-and-runtime-packaging)

## What Changed In The Database Migration

The application no longer depends on a local SQLite file for runtime persistence.

The migration introduced:

- a central config resolver in [api/config.py](/home/repos/ideagen-saas-aws/api/config.py)
- SQLAlchemy models in [api/database/models.py](/home/repos/ideagen-saas-aws/api/database/models.py)
- Alembic migrations in [alembic](/home/repos/ideagen-saas-aws/alembic)
- Postgres-backed persistence helpers in [api/db.py](/home/repos/ideagen-saas-aws/api/db.py)
- an app startup wrapper in [scripts/start_server.sh](/home/repos/ideagen-saas-aws/scripts/start_server.sh) that runs `alembic upgrade head` before starting `uvicorn`
- Terraform-managed RDS, Secrets Manager, ECR, App Runner, VPC networking, and deployment workflows

That changed the operational model of the app:

- schema changes are no longer created ad hoc in app startup code
- schema ownership is now Alembic
- production data lives in managed Postgres, not inside the container filesystem
- local development uses the same database engine as production

For the full persistence explanation, see [ARCHITECTURE.md](/home/repos/ideagen-saas-aws/ARCHITECTURE.md#persistence-architecture).

## Environment Model

The backend resolves exactly one effective database URL at startup.

- `APP_ENV=local` -> uses `DATABASE_URL_LOCAL`
- `APP_ENV=prod` -> uses `DATABASE_URL_PROD`

The selection logic is implemented in [api/config.py](/home/repos/ideagen-saas-aws/api/config.py).

Important behavior:

- if `APP_ENV=local`, `DATABASE_URL_LOCAL` is required
- if `APP_ENV=prod`, `DATABASE_URL_PROD` is required
- if `APP_ENV` is omitted, the backend defaults to `local` outside AWS and `prod` when AWS runtime env markers are present

This is separate from Terraform environment selection. The Python app chooses `local` vs `prod`. Terraform chooses which AWS environment, such as `dev`, `test`, or `prod`, is being provisioned or updated.

## Database Ownership And Migrations

Database schema is defined in two layers:

1. SQLAlchemy models in [api/database/models.py](/home/repos/ideagen-saas-aws/api/database/models.py)
2. Alembic migration history in [alembic/versions](/home/repos/ideagen-saas-aws/alembic/versions)

The initial Postgres baseline creates:

- `user_usage`
- `saved_results`
- `saved_rank_reports`
- `saved_comparisons`
- `saved_stakeholder_reports`

The migration also changes storage semantics from SQLite text blobs to Postgres-native types where appropriate:

- JSON payloads are stored as `JSONB`
- timestamps are stored as timezone-aware `timestamptz`
- list and report queries use explicit indexes for dominant access patterns

### Runtime migration behavior

There are two supported ways migrations run:

- local direct backend development:
  - you run `alembic upgrade head` yourself before starting the API
- containerized runtime:
  - [scripts/start_server.sh](/home/repos/ideagen-saas-aws/scripts/start_server.sh) runs `alembic upgrade head` before launching `uvicorn`

This distinction matters:

- if you run `uvicorn index:app` manually, you still need to apply migrations first
- if you run the built container, migrations are executed at container startup as long as a database URL is configured

## Local Development

### 1. Start local PostgreSQL

The repo includes a local Postgres service in [docker-compose.yml](/home/repos/ideagen-saas-aws/docker-compose.yml).

```bash
docker compose up -d postgres
```

### 2. Configure local env

Set at minimum:

```bash
APP_ENV=local
DATABASE_URL_LOCAL=postgresql+psycopg://postgres:postgres@localhost:5432/ideagen_dev
```

Also provide the provider, auth, and email variables used by the app:

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
- `EMAIL_FROM`

### 3. Apply migrations

```bash
alembic upgrade head
```

### 4. Run the backend

```bash
cd api
uvicorn index:app --reload --port 8000
```

### 5. Run the frontend

```bash
npm install
npm run dev
```

This path is the normal development loop when you want maximum visibility into backend and frontend behavior separately.

## Local Docker Run

If you want to run the full container locally against local Postgres:

```bash
docker build \
  --build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY" \
  -t ideagen-app .

docker run -p 8000:8000 \
  -e APP_ENV=local \
  -e DATABASE_URL_LOCAL="$DATABASE_URL_LOCAL" \
  -e CLERK_JWKS_URL="$CLERK_JWKS_URL" \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -e GEMINI_API_KEY="$GEMINI_API_KEY" \
  -e GEMINI_API_URL="$GEMINI_API_URL" \
  -e DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" \
  -e DEEPSEEK_API_URL="$DEEPSEEK_API_URL" \
  -e GROK_API_KEY="$GROK_API_KEY" \
  -e GROK_API_URL="$GROK_API_URL" \
  -e RESEND_API_KEY="$RESEND_API_KEY" \
  -e EMAIL_FROM="$EMAIL_FROM" \
  ideagen-app
```

The container startup script runs Alembic automatically before `uvicorn`, so this is the closest local approximation of the production runtime contract.

## Production Deployment Model

Production assumes this shape:

- the app container is built and pushed to ECR
- App Runner pulls the image and runs the application
- App Runner serves public HTTPS ingress
- App Runner uses a VPC connector for private egress to RDS
- RDS PostgreSQL runs in private subnets
- runtime app secrets live in AWS Secrets Manager
- the RDS master password is AWS-managed in Secrets Manager

Terraform resources for this are defined in [terraform](/home/repos/ideagen-saas-aws/terraform).

The important point is that the application code itself does not change between local and production. The environment changes around it.

## Terraform And Deployment Scripts

The repo includes environment-aware deployment wrappers:

- [scripts/deploy.sh](/home/repos/ideagen-saas-aws/scripts/deploy.sh)
- [scripts/destroy.sh](/home/repos/ideagen-saas-aws/scripts/destroy.sh)

They select the matching environment var-file automatically:

- `terraform/dev.tfvars`
- `terraform/test.tfvars`
- `terraform/prod.tfvars`

Examples:

```bash
./scripts/deploy.sh dev
./scripts/deploy.sh prod
./scripts/destroy.sh dev
```

### What `deploy.sh` does

For a given environment, the local deploy wrapper:

1. loads `.env`
2. bootstraps the Terraform backend bucket and lock table if missing
3. initializes Terraform with the correct remote state key
4. selects the matching Terraform workspace
5. performs first-deploy bootstrap only if App Runner is not already managed in state
6. syncs runtime secrets from local env into AWS Secrets Manager
7. builds and pushes the Docker image to ECR
8. applies Terraform for the App Runner service
9. if App Runner is already `RUNNING`, starts a deployment to pull the new image
10. if Terraform already triggered a rollout, waits for the service to return to `RUNNING`
11. waits for `/health`

This is intentionally different from the earlier design that toggled App Runner off and on. Redeployments now update in place.

For the full infra explanation, see [ARCHITECTURE.md](/home/repos/ideagen-saas-aws/ARCHITECTURE.md#deployment-and-runtime-packaging).

## GitHub Actions

The repo includes:

- CI: [.github/workflows/ci.yml](/home/repos/ideagen-saas-aws/.github/workflows/ci.yml)
- deploy: [.github/workflows/deploy.yml](/home/repos/ideagen-saas-aws/.github/workflows/deploy.yml)
- destroy: [.github/workflows/destroy.yml](/home/repos/ideagen-saas-aws/.github/workflows/destroy.yml)

Current behavior:

- CI runs backend tests, frontend lint, Terraform validation, and Docker build checks
- deploy workflow supports `dev`, `test`, and `prod`
- destroy workflow is manual-only and requires explicit confirmation

The deploy workflow is the automated version of the same operational contract used by the local deployment scripts: prepare state, reconcile infrastructure, synchronize secrets, publish the image, roll the service, and verify health.

## Custom Domain And Host Allowlist

The production custom domain is:

- `https://ideagen.agentairg.site`

The backend enforces request host allowlisting. That is controlled by `ALLOWED_HOSTS` and implemented in [api/index.py](/home/repos/ideagen-saas-aws/api/index.py).

Important behavior:

- `/health` is exempt so App Runner health probes continue to work
- normal app/API traffic is rejected if the request host is not allowed
- wildcard hosts such as `*.awsapprunner.com` are supported for controlled access during rollout and validation

## Key Runtime Files

- backend config: [api/config.py](/home/repos/ideagen-saas-aws/api/config.py)
- DB access layer: [api/db.py](/home/repos/ideagen-saas-aws/api/db.py)
- SQLAlchemy models: [api/database/models.py](/home/repos/ideagen-saas-aws/api/database/models.py)
- Alembic baseline: [alembic/versions/20260319_000001_initial_postgres_schema.py](/home/repos/ideagen-saas-aws/alembic/versions/20260319_000001_initial_postgres_schema.py)
- container startup: [scripts/start_server.sh](/home/repos/ideagen-saas-aws/scripts/start_server.sh)
- Terraform infra: [terraform/main.tf](/home/repos/ideagen-saas-aws/terraform/main.tf)
- main architecture reference: [ARCHITECTURE.md](/home/repos/ideagen-saas-aws/ARCHITECTURE.md)

## Related Documentation

- architecture: [ARCHITECTURE.md](/home/repos/ideagen-saas-aws/ARCHITECTURE.md)
- API reference: [api_reference.md](/home/repos/ideagen-saas-aws/api_reference.md)
- backend technical guide: [technical_backend.md](/home/repos/ideagen-saas-aws/technical_backend.md)
- data model: [data_model.md](/home/repos/ideagen-saas-aws/data_model.md)
- deployment runbook: [deployment_runbook.md](/home/repos/ideagen-saas-aws/deployment_runbook.md)
- Terraform guide: [terraform/README.md](/home/repos/ideagen-saas-aws/terraform/README.md)
- current usage and quota behavior: [current_usage.md](/home/repos/ideagen-saas-aws/current_usage.md)
- security and privacy notes: [security_privacy.md](/home/repos/ideagen-saas-aws/security_privacy.md)
- stakeholder dossier schema: [stakeholder_report_schema.md](/home/repos/ideagen-saas-aws/stakeholder_report_schema.md)
