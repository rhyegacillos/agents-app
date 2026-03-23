# Technical Backend Documentation

This document describes the backend as it exists after the PostgreSQL migration.

The focus is on:

- request orchestration in FastAPI
- agent execution patterns
- Postgres persistence and migration ownership
- how the frontend interacts with the backend

## 1. Backend Runtime Overview

Main backend entrypoints:

- API application: [api/index.py](/home/repos/ideagen-saas-aws/api/index.py)
- app config: [api/config.py](/home/repos/ideagen-saas-aws/api/config.py)
- persistence layer: [api/db.py](/home/repos/ideagen-saas-aws/api/db.py)
- SQLAlchemy models: [api/database/models.py](/home/repos/ideagen-saas-aws/api/database/models.py)
- startup wrapper: [scripts/start_server.sh](/home/repos/ideagen-saas-aws/scripts/start_server.sh)

Runtime shape:

```text
FastAPI
  -> auth verification
  -> rate-limit and quota checks
  -> provider routing
  -> agent orchestration
  -> persistence
  -> PDF/email delivery
```

## 2. Storage Architecture

The backend no longer uses SQLite.

Current storage stack:

- PostgreSQL database
- SQLAlchemy 2.x models and sessions
- Alembic-managed schema

Production database target:

- Amazon RDS for PostgreSQL

Local database target:

- Docker Compose PostgreSQL

### Why this matters

This change removes the old limitations of local-file SQLite in an App Runner environment:

- container-local storage is not treated as durable persistence
- multiple instances can share the same database
- migrations are explicit and versioned
- connection management is centralized

## 3. Database Configuration Resolution

[api/config.py](/home/repos/ideagen-saas-aws/api/config.py) resolves a single effective `database_url`.

Inputs:

- `APP_ENV`
- `DATABASE_URL_LOCAL`
- `DATABASE_URL_PROD`
- optional pool tuning vars

Behavior:

- `APP_ENV=local` -> `DATABASE_URL_LOCAL`
- `APP_ENV=prod` -> `DATABASE_URL_PROD`
- invalid combinations fail fast at startup

The resolved settings object also controls:

- `DB_POOL_SIZE`
- `DB_MAX_OVERFLOW`
- `DB_POOL_TIMEOUT`
- `DB_POOL_RECYCLE`
- `DB_ECHO`

## 4. Schema Ownership

Schema ownership moved to Alembic.

Relevant files:

- Alembic config: [alembic.ini](/home/repos/ideagen-saas-aws/alembic.ini)
- migration environment: [alembic/env.py](/home/repos/ideagen-saas-aws/alembic/env.py)
- baseline migration: [alembic/versions/20260319_000001_initial_postgres_schema.py](/home/repos/ideagen-saas-aws/alembic/versions/20260319_000001_initial_postgres_schema.py)

Important backend rule:

- the app should never depend on ad hoc runtime schema mutation as the source of truth
- schema drift is resolved by Alembic revisions

Current container startup behavior:

- [scripts/start_server.sh](/home/repos/ideagen-saas-aws/scripts/start_server.sh) runs `alembic upgrade head`
- then launches `uvicorn`

This was added specifically to prevent production startup against an empty Postgres schema.

## 5. Database Model Summary

[api/database/models.py](/home/repos/ideagen-saas-aws/api/database/models.py) defines:

- `UserUsage`
- `SavedResult`
- `SavedRankReport`
- `SavedComparison`
- `SavedStakeholderReport`

Notable Postgres-specific changes:

- JSON payloads are stored as `JSONB`
- timestamps are stored as timezone-aware datetimes
- usage counters use numeric columns with check constraints
- list/read access paths have explicit indexes by `user_id` and `created_at`

## 6. Persistence Behavior (`api/db.py`)

The backend persistence layer keeps the same product-facing behavior while changing the storage engine.

### 6.1 Usage and quota handling

`user_usage` remains the authoritative source for:

- total token accumulation
- per-window API call counters
- per-day email counters
- plan-aware resets

The main difference now is that the data is updated in Postgres through SQLAlchemy instead of SQLite helper calls.

### 6.2 Saved artifacts

The artifact tables remain conceptually the same:

- `saved_results`
- `saved_comparisons`
- `saved_rank_reports`
- `saved_stakeholder_reports`

What changed:

- JSON payloads are stored natively instead of stringified text blobs
- timestamp ordering is based on actual Postgres datetime columns
- indexes are present for the dominant read paths

### 6.3 Snapshot durability

The application still stores report snapshots so views and PDFs can continue to render even if underlying source runs change or are deleted.

That design did not change in the migration. What changed is the storage engine and schema management discipline around it.

## 7. LLM Client and Fallback Architecture

[api/index.py](/home/repos/ideagen-saas-aws/api/index.py) configures:

- `openai_client`
- `google_client`
- `deepseek_client`
- `grok_client`

Model chains are defined in `FALLBACK_CHAINS`.

Current primary model IDs include:

- `grok-4-1-fast-reasoning`
- `gemini-2.5-flash`
- `gpt-5-nano`
- `deepseek-chat`

Each chain has an explicit fallback model. The shared fallback execution is implemented in [api/agent/model_fallback.py](/home/repos/ideagen-saas-aws/api/agent/model_fallback.py).

## 8. Agent Orchestration

There is still no external queue or autonomous multi-agent runtime.

The backend uses request-scoped orchestration:

- endpoint receives request
- backend validates auth/limits
- backend chooses provider/model flow
- backend orchestrates agent(s)
- backend persists outputs
- backend returns response

### 8.1 Idea generation

Endpoint:

- `POST /api`

Behavior:

1. check API quota with `user_usage`
2. resolve requested model/provider labels
3. run one generation coroutine per selected model
4. apply provider fallback chains and validation retries
5. optionally run ranking for the multi-model output set
6. aggregate token usage
7. persist or return output for frontend auto-save

### 8.2 Compare results

Endpoint:

- `POST /api/compare-results`

Behavior:

1. load two saved runs
2. backfill rank data if missing
3. resolve the top output from each run
4. run comparison agent
5. persist comparison artifact

### 8.3 Decision summary

Endpoint:

- `POST /api/rank-report`

Behavior:

1. load selected saved runs
2. reuse cached report when the run-set cache key matches
3. otherwise run the decision summary agent
4. persist report plus run snapshot

### 8.4 Execution plan

Endpoint:

- `POST /api/stakeholder-report`

Behavior:

1. resolve source evidence from saved artifact(s)
2. resolve the selected winning output variant
3. build deterministic finance baseline and bounded adjustments
4. generate narrative sections with the configured model chain
5. merge finance + narrative + provenance
6. persist execution plan dossier

## 9. Frontend-to-Backend Contract

The main UI in [pages/product.tsx](/home/repos/ideagen-saas-aws/pages/product.tsx) depends on:

- `POST /api`
- `GET/POST/DELETE /api/saved-results`
- `POST /api/compare-results`
- `GET/DELETE /api/compare-results`
- `POST /api/rank-report`
- `GET/DELETE /api/rank-reports`
- `POST /api/stakeholder-report`
- `GET/DELETE /api/stakeholder-reports`
- report PDF/email endpoints

The migration to Postgres was intentionally designed not to change those HTTP contracts in phase 1.

## 10. Logging and Operational Signals

The backend logs:

- provider/model fallback events
- validation failures
- report generation events
- auth failures
- startup migration events

Important runtime logs now include:

- `Running Alembic migrations`
- migration revision upgrade logs
- `Starting uvicorn`

In AWS, these are visible in CloudWatch through the App Runner application log group.

## 11. Security-Relevant Backend Behavior

- Clerk JWT verification is handled in [api/index.py](/home/repos/ideagen-saas-aws/api/index.py)
- host allowlist enforcement is also in [api/index.py](/home/repos/ideagen-saas-aws/api/index.py)
- secrets are injected through environment variables / Secrets Manager, not hardcoded in code
- database credentials are selected from env and not embedded in the image

## 12. What to Read Next

- architecture overview: [ARCHITECTURE.md](/home/repos/ideagen-saas-aws/ARCHITECTURE.md)
- data model details: [data_model.md](/home/repos/ideagen-saas-aws/data_model.md)
- deployment runbook: [deployment_runbook.md](/home/repos/ideagen-saas-aws/deployment_runbook.md)
- Terraform guide: [terraform/README.md](/home/repos/ideagen-saas-aws/terraform/README.md)
