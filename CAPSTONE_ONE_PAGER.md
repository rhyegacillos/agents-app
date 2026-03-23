# IdeaGen One-Pager (AI Engineer Capstone)

## Documentation Sync: Adaptive Decision Flow + Step Guide (2026-02-20)

This document is synchronized with the latest UX/flow implementation in `pages/product.tsx`.

- **Adaptive flow modes**: UI now shifts between `guided` and `status` modes.
- **Hysteresis guard**: mode switching uses `guided -> status` at `<= 40` and `status -> guided` at `>= 60` to avoid flip-flop around a single threshold.
- **Persistent Step Guide**: every workspace step includes a structured guide panel (`What you do`, `What you get`, `When to use`, `To move forward`).
- **Per-step memory**: collapse/expand is saved per user and per step using local storage (`collapsedByStep`, `touchedByStep`).
- **Adaptive Step Guide defaults**: untouched guides auto-expand in guided mode and auto-collapse in status mode.
- **User override priority**: once a user manually toggles a step guide, that preference is preserved and not auto-overridden.
- **Generated empty-state scenarios**: first-time vs returning-with-library cases are explicitly separated for clearer onboarding.
- **Decision Summary behavior**: supports single-run and multi-run (1-5) synthesis; compare-first is recommended but not mandatory.
- **Compare behavior**: compares two selected saved runs and surfaces winner/diff insight; best quality when config alignment is preserved.
- **Execution handoff**: Decision Summary remains the source artifact for Execution Plan generation and export workflow.
- **Scope note**: this update is primarily frontend UX/state orchestration; backend endpoint contracts remain unchanged unless otherwise stated in backend/API docs.


## Executive Summary
IdeaGen is a production-style AI decision platform that converts raw LLM ideation into structured, auditable business decisions. The system supports multi-model generation, ranking, run-to-run comparison, decision summaries, and a final Execution Plan artifact (positioned as an **Investment Readiness Assessment**). It is designed to move from "interesting idea text" to "stakeholder-ready plan" with clear gates, saved evidence, and exportable deliverables.

## Problem
Most ideation tools stop at single-shot generation. That is insufficient for business decisions because teams need:

- comparative evaluation across models and runs
- persistent artifacts they can reload and defend
- explicit rationale for why one direction is stronger
- report outputs suitable for stakeholder review
- predictable behavior under model/provider instability

## Solution
IdeaGen uses a deterministic backend orchestrator (FastAPI) plus specialized agent workflows.

Pipeline:

1. Generate ideas across selected providers.
2. Rank model outputs for each run.
3. Compare top outputs between runs.
4. Build a Decision Summary from selected runs.
5. Build an Execution Plan from saved evidence.

The latest implementation adds **Grounded Finance v2**:

- deterministic finance computation for cost/profit sections
- deterministic run-conditioned assumption adjustments (constraints/persona/output-confidence)
- LLM narrative generation for strategic framing and plan wording
- proposal disclaimer + sensitivity analysis to communicate estimate boundaries

This hybrid design improves realism without losing narrative quality.

## Key Capabilities
- Multi-provider generation: OpenAI, Gemini, DeepSeek, Grok
- Per-run ranking with scored ordering and rationale
- Diff insight between run A and run B top-ranked outputs
- Decision Summary report over selected runs
- Execution Plan generation with `go / conditional_go / no-go`
- Execution Plan framed as an **Investment Readiness Assessment** for stakeholder approval decisions
- Execution Plan card-level `Info` pill tooltips (plain-English guidance per panel)
- PDF export (all report types) + presentation-style PDF for Execution Plan
- Saved artifact lifecycle (`View`, `Delete`, `Delete All`) with guarded modal UX
- Plan-aware usage controls (tokens, API calls, email, storage)

## AI Engineering Patterns Demonstrated
- **Orchestrator-worker architecture**: route-level orchestration + task-specific agents.
- **Contract-first outputs**: HTML/JSON schema boundaries per workflow.
- **Validation + correction loops**: invalid outputs are retried with structured repair prompts.
- **Fallback chains**: ordered provider/model fallback for resiliency.
- **Cache-before-infer**: comparisons and reports reused when keys match.
- **Snapshot durability**: decision artifacts remain valid even if source runs change.
- **Deterministic finance + narrative split**: grounded calculations with LLM explanation layer.

## Why Grounded Finance v2 Matters
Execution plans often look polished but can include invented numbers if fully model-generated. Grounded Finance v2 addresses that by enforcing deterministic financial sections and preserving AI only for narrative interpretation.

Practical effect:

- reproducible numbers for the same assumptions
- meaningful per-report variation (not flat industry-only projections)
- clearer decision gates
- less hallucination risk in budget/profit projections
- better stakeholder trust via provenance and assumption traceability

## Architecture Snapshot
- Frontend: Next.js + React + TypeScript
- Backend: FastAPI orchestration layer
- Persistence: **PostgreSQL** (system of record) via **SQLAlchemy 2.x** ORM and session layer
- Schema: **Alembic** only for DDL (`alembic upgrade head` in `scripts/start_server.sh` before `uvicorn` when a DB URL is set); FastAPI `init_db()` checks connectivity (`SELECT 1`), not schema
- Reporting: WeasyPrint (HTML -> PDF)
- Email: Resend
- Auth: Clerk JWT + JWKS verification
- **AWS deployment (highlight)**: **Amazon ECR** (images) → **AWS App Runner** (runtime) → **Amazon RDS for PostgreSQL** (private DB; VPC connector from App Runner) + **AWS Secrets Manager** (e.g. `DATABASE_URL_PROD`, API keys, wired into App Runner as secret-backed env). **Terraform** defines RDS, secrets, and related IAM/networking. **Route 53** + host allowlist for the custom domain.

### Database stack (PostgreSQL + SQLAlchemy + Alembic)

- **PostgreSQL** holds all durable application state: quotas (`user_usage`), saved generation runs (`saved_results`), comparisons (`saved_comparisons`), decision reports (`saved_rank_reports`), and execution / stakeholder dossiers (`saved_stakeholder_reports`). **In AWS production**, that server is **Amazon RDS for PostgreSQL** (managed, typically private subnets); the app reaches it using **`DATABASE_URL_PROD`**, which should be injected from **AWS Secrets Manager** into **App Runner**, not embedded in the container image. Local dev uses Docker Compose Postgres so the **Postgres engine** matches production.

- **SQLAlchemy 2.x** defines **declarative models** in `api/database/models.py` (`Mapped` / `mapped_column`), uses **JSONB** for flexible AI artifact payloads, and applies **indexes and check constraints** in the model layer for list performance and data integrity. `api/database/session.py` builds a pooled engine (`pool_pre_ping`, configurable pool size/overflow/recycle/timeout), exposes a `sessionmaker`, and provides `session_scope()` for bounded sessions. Route and domain logic call into `api/db.py`, which centralizes reads/writes instead of scattering raw SQL.

- **Alembic** (`alembic.ini`, `alembic/env.py`, `alembic/versions/`) is the **only** supported way to evolve schema: new tables/columns/indexes ship as revisions and apply with `alembic upgrade head`. `scripts/start_server.sh` runs migrations automatically before the API starts when `DATABASE_URL_LOCAL` or `DATABASE_URL_PROD` is present, reducing “empty RDS on first deploy” failures.

- **Startup split (matches `ARCHITECTURE.md` §6)**: **Migrations** run in the shell entrypoint **before** the process binds to port 8000. **FastAPI** `startup` calls `db.init_db()`, which only **verifies** the pool can talk to Postgres—it does **not** run DDL. Running raw `uvicorn` without Alembic first can pass startup yet break on first query if tables are missing.

- **Configuration**: `api/config.py` selects a single `database_url` from `APP_ENV` plus `DATABASE_URL_LOCAL` or `DATABASE_URL_PROD` (documented URL form `postgresql+psycopg://...`). Optional pool overrides: `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE`, `DB_ECHO`. Optional **SQLite → Postgres** one-time import: `scripts/import_sqlite_to_postgres.py`; normal runtime is Postgres-only.

## Production-Like Controls and UX
- API/token/email/storage quota enforcement
- premium feature gating at UI + backend layers
- locked modal states during critical operations
- skeleton/spinner/dot loading feedback
- draggable, viewport-constrained saved-results shell
- in-context, panel-level info pills to improve readability for non-technical stakeholders

## Deployment Notes
- **Amazon RDS for PostgreSQL**: production system of record; App Runner uses **VPC connector** / private networking to connect (not a public DB endpoint in the intended design).
- **AWS Secrets Manager**: store **`DATABASE_URL_PROD`** and sensitive API keys; reference them from **App Runner** so the container receives env vars without baking secrets into **ECR** images.
- **Amazon ECR** + **AWS App Runner**: build/push image, then run the service with auto deploy from ECR where configured.
- Custom domain: `ideagen.agentairg.site` (**Route 53** + App Runner custom domain)
- Host allowlist enforced by `ALLOWED_HOSTS`
- Health endpoint: `/health`
- **Container / scripted entry**: `scripts/start_server.sh` runs **Alembic** then **Uvicorn**; FastAPI startup only **pings** the database (migrations hit **RDS** when `DATABASE_URL_PROD` points there)

## Primary Code References
- `api/index.py` (route orchestration, grounded finance, validation; startup `init_db()` = DB connectivity check only)
- `api/agent/*.py` (generation/rank/compare/report/recommendation/email agents)
- `api/config.py` (effective database URL and pool tuning)
- `api/database/models.py` (SQLAlchemy ORM / table definitions)
- `api/database/session.py` (engine, pooling, sessions)
- `api/db.py` (persistence and usage/limit tracking)
- `alembic/` (schema migrations)
- `scripts/start_server.sh` (migrations then server)
- `api/utils/pdf_utils.py` (PDF and presentation renderers)
- `pages/product.tsx` (workspace UX and report workflows)
- `ARCHITECTURE.md` (full technical deep dive; **§6** = PostgreSQL + SQLAlchemy + Alembic persistence)
