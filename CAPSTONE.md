# IdeaGen: Agentic Multi-Model Decision Platform

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


## Portfolio Capstone for AI Engineer Applications

## 1. Project Overview

IdeaGen is a production-style AI application that turns raw LLM generation into a structured decision workflow.
Users can generate ideas across multiple model providers, rank outputs, compare saved runs, and produce execution-ready stakeholder reports (Execution Plan / Investment Readiness Assessment + PDF/Presentation exports).

This project demonstrates end-to-end AI engineering:

- multi-provider model orchestration,
- contract-first agent outputs,
- validation and retry loops,
- deterministic fallback behavior,
- cached decision artifacts,
- user-level quotas and plan gating,
- complete product UX and deployment packaging.

---

## 2. Problem Statement

Most AI idea tools stop at single-shot text generation. That fails in real decision environments because teams need:

- cross-model comparison,
- repeatable saved artifacts,
- explicit rationale for choosing one direction over another,
- exportable reports for non-technical stakeholders,
- predictable behavior under provider instability.

IdeaGen addresses that gap by implementing an opinionated decision pipeline, not just a prompt wrapper.

---

## 3. My Role and Scope

I owned architecture and implementation across backend, AI workflows, data model, and frontend product behavior.

Primary ownership:

- API orchestration and agent pipeline design (`api/index.py`)
- agent modules for generation, ranking, comparison, reporting, recommendation, and email (`api/agent/*.py`)
- persistence and quotas backed by PostgreSQL: SQLAlchemy models and session lifecycle (`api/database/models.py`, `api/database/session.py`), repository-style helpers (`api/db.py`), environment-driven DB URL resolution (`api/config.py`), and versioned schema evolution (`alembic/`)
- reporting and PDF generation (`api/utils/pdf_utils.py`)
- workspace UX, saved-results modal workflows, and delivery actions (`pages/product.tsx`)
- Dockerized deployment path and runtime integration (`Dockerfile`, `next.config.ts`)
- architecture and technical documentation

---

## 4. Architecture Summary

```text
Browser (Next.js static UI)
  -> FastAPI API
      -> Auth verification (Clerk JWT + JWKS)
      -> Quota and plan checks (PostgreSQL / SQLAlchemy)
      -> Agent orchestration
      -> PDF rendering (WeasyPrint)
      -> Email dispatch (Resend)
  -> LLM providers (OpenAI, Gemini, DeepSeek, Grok)

AWS production (typical): ECR image -> App Runner service
  -> env from Secrets Manager (DATABASE_URL_PROD, API keys) + plain config
  -> DATABASE_URL_PROD -> Amazon RDS for PostgreSQL (private; VPC connector)
```

Core runtime properties:

- Single Docker image serving both static frontend and API
- PostgreSQL persistence for usage and artifacts
- Alembic-managed schema migrations
- Route-level orchestration (no external queue in current version)
- User-scoped saved artifacts and usage meters

---

## 5. Technology Stack

Frontend:

- Next.js (static export), React, TypeScript
- Clerk for auth session/token access

Backend:

- FastAPI, Python
- OpenAI SDK + Google GenAI SDK (provider integrations)
- PostgreSQL + SQLAlchemy for usage and artifact persistence
- Alembic for schema migrations
- WeasyPrint for HTML-to-PDF
- Resend for transactional email

Deployment:

- Multi-stage Docker build
- Uvicorn runtime
- Health endpoint and Docker healthcheck
- **Amazon RDS for PostgreSQL** (managed relational DB in VPC; not co-located with the container)
- **AWS Secrets Manager** for production secrets (including **`DATABASE_URL_PROD`** and provider API keys, provisioned via Terraform and wired into **AWS App Runner**)
- **Terraform**-managed AWS infrastructure (ECR, App Runner, RDS, secrets, networking)

---

## 6. Product Features Delivered

1. Multi-model idea generation for one configuration (industry, constraints, persona).
2. Per-run ranking with summary, highlights, and scored model ordering.
3. Saved results lifecycle: create, list, load, delete.
4. Compare Results mode (Run A vs Run B) with top-output diff insight.
5. Decision Summary Report across selected runs (or all runs).
6. Execution Plan generation from saved decision artifacts with grounded finance mode.
7. PDF export and email delivery for generated, compare, and decision artifacts, plus PDF/Presentation export for execution plans.
8. Premium-only recommendation for persona + constraints.
9. Usage tracking and plan-aware limits (API calls, tokens, emails, saved storage).
10. Draggable Saved Results floating modal with generated/compare/decision/execution modes.
11. Per-item and bulk artifact deletion (`Delete`, `Delete All`) for generated runs, comparisons, decision reports, and execution plans.
12. Progressive loading UX states: skeleton hydration, footer status messages, spinner/dot indicators, and modal lock during critical operations.
13. Proposal disclaimer + sensitivity analysis in execution outputs for benchmark-based realism communication.
14. Card-level `Info` pill tooltips on Execution Plan panels for plain-English interpretation of each report section.
15. Execution Plan is positioned as an **Investment Readiness Assessment** to frame go/no-go, financial gates, and implementation readiness in one artifact.

---

## 7. Core Agentic AI Development Patterns

### Pattern A: Orchestrator-Worker Architecture

FastAPI endpoints are the deterministic orchestrator; feature-specific agents are workers.

- Orchestrator responsibilities: auth, gating, sequencing, persistence, response shaping.
- Worker responsibilities: task-specific reasoning, structured output generation.

This keeps business behavior predictable while still using LLMs for specialized analysis.

### Pattern B: Contract-First Outputs

Agent outputs are treated as contracts, not free-form text.

- generation: HTML output contract
- ranking/comparison/report/recommendation: JSON contract with required fields

Invalid outputs are not accepted as successful results.

### Pattern C: Validation-Driven Retry

Each analysis agent retries with explicit correction feedback when validation fails.

Typical flow:

1. call model
2. parse output
3. validate schema/content
4. if invalid, append validation errors and retry

This materially improves robustness versus blind retries.

### Pattern D: Multi-Provider Fallback

The system uses ordered model fallback chains per provider family (`FALLBACK_CHAINS` + `generate_with_fallback`).

- transient non-timeout failures: fallback to next model
- timeout failures: retry context, not silent provider switch
- hard non-transient failures: fail fast

### Pattern E: Progressive Analysis Pipelines

Instead of one large prompt, the system composes stages:

- generate -> rank (single run)
- ensure rank -> select top outputs -> compare (two runs)
- load run set -> synthesize report -> deliver artifact

This produces decision-grade artifacts with traceable intermediate structure.

### Pattern F: Deterministic Safety Fallbacks

Each analysis module has fallback payload behavior:

- fallback ranking
- fallback comparison
- fallback decision report
- fallback recommendation selection
- fallback email payload

Practical effect:

- UI remains functional under partial model failure.
- Users receive structured outputs instead of dead-end errors.
- Delivery flows continue even if one AI step fails.

### Pattern G: Cache-Before-Infer

Expensive analysis is reused when possible.

- compare artifacts cached by run pair
- decision reports cached by normalized run ID key

Cache miss triggers inference; cache hit returns existing artifact and avoids extra token cost.

### Pattern H: Snapshot-Based Artifact Durability

Decision reports store run snapshots (`runs_json`) so historical reports remain renderable even if source runs later change or are deleted.

### Pattern I: Deterministic Finance + Narrative Split

Execution Plan generation uses a hybrid architecture:

- deterministic finance engine for budgets, unit economics, projections, scenario outcomes, and gate math
- LLM narrative generation for thesis framing, blueprint language, and risk narrative

This removes free-form financial invention while preserving high-quality narrative output.

---

## 8. Workflow Deep Dive

### 8.1 Idea Generation (`POST /api`)

1. Verify auth and enforce API/token limits.
2. Build prompts from selected configuration.
3. Resolve requested model labels to concrete model IDs.
4. Execute model generation concurrently.
5. Validate output per model through generation agent.
6. Aggregate usage.
7. Run ranking agent for multi-model outputs.
8. Return results + ranking + usage.
9. Frontend auto-saves result set.

### 8.2 Compare Results (`POST /api/compare-results`)

1. Validate two distinct run IDs.
2. Enforce same-config requirement (industry/persona/constraints/model set).
3. Return cached comparison if available.
4. Backfill missing rank data if needed.
5. Select top output from each run.
6. Run compare agent and persist outcome.

### 8.3 Decision Summary (`POST /api/rank-report`)

1. Validate output mode (`pdf`, `email`, `both`) and input run set.

### 8.4 Execution Plan (`POST /api/stakeholder-report`)

1. Validate source artifact (`decision_report`, `compare_result`, or `saved_run`) and selection context.
2. Validate `finance_mode` (`grounded_v2` default, `llm_v1` compatibility).
3. Build deterministic baseline dossier from assumption packs and scenario profile.
4. Apply deterministic run-conditioned adjustments (constraints/persona/output signals/model confidence) with bounded multipliers.
5. Recompute projections, scenario probability mix, and funnel assumptions from adjusted assumptions.
4. Compose narrative sections via LLM (thesis, blueprint language, risks, actions).
6. Merge narrative with deterministic finance sections.
7. Validate/normalize dossier and enforce decision gates (`go`, `conditional_go`, `no_go`).
8. Persist dossier and assumptions snapshot (including adjustment/audit metadata).
9. Support export endpoints:
   - `/api/stakeholder-reports/{id}/pdf`
   - `/api/stakeholder-reports/{id}/presentation`
2. Enforce token and email limits.
3. Resolve cached report by normalized run-set key.
4. On cache miss, run report agent and store snapshot.
5. Render PDF and optionally send email.
6. Return stream or JSON status depending on requested mode.

### 8.4 Recommendation (`POST /api/recommend-combination`)

1. Premium gate enforced server-side.
2. Recommendation agent constrained to allowed options.
3. Strict exact-match checks for persona and constraints.
4. Return recommendation and explanation HTML.

### 8.5 Artifact Deletion and Bulk Cleanup

Single-delete endpoints:

- `DELETE /api/saved-results/{id}`
- `DELETE /api/compare-results/{id}`
- `DELETE /api/rank-reports/{id}`

Bulk-delete endpoints:

- `DELETE /api/saved-results`
- `DELETE /api/compare-results`
- `DELETE /api/rank-reports`

Frontend behavior:

1. All delete actions require explicit user confirmation.
2. Bulk delete returns `{ status, count }` and drives user feedback messaging.
3. During bulk deletion, list rows transition to a pending-delete animation and conflicting actions are disabled.
4. Outside-click handlers are paused for parent modal close while delete confirmations are open.

---

## 9. Reliability Engineering and Guardrails

### 9.1 Reliability Controls

- output validation before persistence/use
- bounded retries with correction feedback
- deterministic fallbacks for each analysis path
- cache reuse for expensive analysis artifacts
- token usage accounting for cost visibility

### 9.2 Product Guardrails

- auth enforced with Clerk JWT verification
- premium-only routes protected on backend
- plan-aware quotas:
  - API calls/minute
  - monthly tokens
  - daily emails
  - saved storage bytes

### 9.3 UX Guardrails

- disabled actions when limits are reached
- loading and lock states for long-running operations
- modal behavior designed to prevent conflicting actions during processing
- delete confirmations isolate destructive flows from accidental parent modal close
- compare/report footers expose explicit in-progress state instead of idle-ready messaging
- execution-plan cards expose in-context plain-English `Info` pill guidance for non-technical readers

---

## 10. Data Model and Persistence Strategy (PostgreSQL + SQLAlchemy + Alembic)

The capstone treats the database as a first-class production concern: a managed **PostgreSQL** instance is the system of record, **SQLAlchemy 2.x** is the application access layer, and **Alembic** owns schema history and upgrades. This trio replaces an earlier SQLite-in-container pattern and is what makes horizontal scaling, RDS deployment, and reviewable schema changes realistic for portfolio and interview conversations.

The longest-form technical treatment of this stack (connection flow, pool semantics, Alembic vs `init_db()`, and table-level reference) is **`ARCHITECTURE.md` §6**.

### 10.1 Why PostgreSQL (not filesystem SQLite)

- **Durability and ops**: Data survives container restarts and redeploys; production targets **Amazon RDS for PostgreSQL** (private subnets, Terraform-provisioned) rather than a file inside the image.
- **Concurrency**: Multiple App Runner instances (or local workers) can share one database with ACID semantics and row-level locking where needed.
- **Rich types**: Artifact payloads use **native JSONB** (`sqlalchemy.dialects.postgresql.JSONB`) for structured blobs with efficient indexing and Postgres-native JSON operators when queries evolve.
- **Integrity**: Check constraints and indexes are declared alongside models (for example non-negative usage counters, allowed `source_type` values on execution-plan rows) so the database enforces invariants, not only Python validators.

### 10.2 SQLAlchemy 2.x: how the app talks to Postgres

- **Declarative ORM models** live in `api/database/models.py`: mapped columns use `Mapped[...]` / `mapped_column`, aligned with SQLAlchemy 2 style. Tables include `user_usage`, `saved_results`, `saved_comparisons`, `saved_rank_reports`, and `saved_stakeholder_reports` (execution plans / stakeholder dossiers).
- **Engine and sessions** are centralized in `api/database/session.py`: a single lazily created engine from `create_engine(settings.database_url, future=True)`, **connection pooling** (`pool_size`, `max_overflow`, `pool_pre_ping`, `pool_recycle`, `pool_timeout` from settings), and a `sessionmaker` with `autoflush=False` and `expire_on_commit=False` so long-lived in-memory objects behave predictably after commit.
- **Session lifecycle**: route-level and helper code typically uses `session_scope()` (context manager: create session, yield, always close) so connections return to the pool and transactions are bounded.
- **Repository-style API**: `api/db.py` implements the persistence operations the FastAPI layer calls (load/save/delete artifacts, usage accounting, user-scoped listing). It uses the ORM models and sessions rather than raw SQL scattered through the codebase—keeping SQLAlchemy as the single abstraction over the wire protocol.

### 10.3 Configuration: one effective database URL

`api/config.py` resolves **one** `database_url` at runtime from `APP_ENV`:

- `APP_ENV=local` → `DATABASE_URL_LOCAL` (e.g. Docker Compose Postgres on the developer machine).
- `APP_ENV=prod` → **`DATABASE_URL_PROD`**, which in the **AWS** path should be the full SQLAlchemy URL to **Amazon RDS** (host, port, database, user, password), typically **injected via AWS Secrets Manager** into **App Runner**—provisioned by **Terraform** (`terraform/secrets.tf`), not checked into source control.

The driver stack uses the **`postgresql+psycopg`** SQLAlchemy URL form (Psycopg 3) in documented examples. Same engine family locally and in production reduces “works on my machine” drift.

Optional **pool tuning** (read by `get_settings()` and passed to `create_engine`): `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE`, and `DB_ECHO`. **`pool_pre_ping`** is enabled in code so idle or dropped connections to RDS are less likely to surface as mysterious request failures.

### 10.4 Alembic and FastAPI startup: who does what

- **Ownership**: The canonical **shape** of the database is defined by Alembic **revision files** under `alembic/versions/` (with `alembic.ini` and `alembic/env.py` wiring metadata and `target_metadata` from the SQLAlchemy `Base`).
- **Workflow**: New columns, tables, indexes, or constraints are added by generating a new revision and applying `alembic upgrade head`. That history is diffable in PRs and replayable across dev, staging, and prod.
- **Deploy integration**: `scripts/start_server.sh` runs `alembic upgrade head` **before** `uvicorn` when `DATABASE_URL_LOCAL` or `DATABASE_URL_PROD` is set, so fresh RDS instances or new containers do not serve traffic against an empty or stale schema.
- **FastAPI `init_db()` is not DDL**: On app startup, `api/index.py` calls `db.init_db()`, which **only** runs `verify_database_connection()` (a `SELECT 1` through the SQLAlchemy engine). It does **not** create or migrate tables. Schema must already match **head** from Alembic—or the first real query will fail even though startup “succeeded.” Local bare-metal `uvicorn` without `start_server.sh` still requires the developer to run `alembic upgrade head` first (see README / runbooks).

### 10.5 Data design summary (what lives where)

| Area | Role |
|------|------|
| `user_usage` | Per-user plan, token totals, API call windows, email counts—**quota enforcement** and metering. |
| `saved_results` | Generated runs: config + `results_json` + optional `rank_result_json`. |
| `saved_comparisons` | Pairwise compare artifacts keyed by run IDs. |
| `saved_rank_reports` | Decision summaries with **snapshot** fields (`runs_json`, `report_json`) for reproducibility. |
| `saved_stakeholder_reports` | Execution plans / stakeholder dossiers with `dossier_json`, `assumptions_json`, and typed `source_type` linkage. |

Cross-cutting choices: **user-scoped** queries everywhere for isolation; **JSONB** for fast evolution of AI-shaped payloads; **indexes** on `(user_id, created_at)` and domain keys (e.g. compare pair, report cache key) for list and lookup performance.

### 10.6 Optional migration path from legacy SQLite

For one-time imports from an older SQLite deployment, the repo includes `scripts/import_sqlite_to_postgres.py`. Normal runtime paths read and write **only** PostgreSQL through SQLAlchemy.

---

## 11. Security and Operational Considerations

Security controls implemented:

- JWT signature verification via JWKS
- user-scoped data access in persistence layer
- server-side plan/feature enforcement
- secrets loaded from environment variables

Operational controls:

- `/health` endpoint
- Docker healthcheck
- **Schema**: `alembic upgrade head` via `scripts/start_server.sh` before `uvicorn` when a DB URL is configured
- **Connectivity**: FastAPI startup `db.init_db()` verifies the pool can reach Postgres (no DDL)
- structured logs around generation, fallback, validation, and delivery paths

---

## 12. Frontend Engineering Notes

The product workspace (`pages/product.tsx`) manages:

- configuration inputs and advanced settings
- generated/compare/decision/execution tabs
- saved-results modal with four modes
- draggable modal behavior with viewport constraints
- per-row `View/Delete` actions for saved generated runs, comparisons, decision reports, and execution plans
- mode-specific `Delete All` controls with confirmation and empty-state disable
- fixed action footers for compare/decision generation and execution-selector workflows
- animated status indicators (`LoadingDots`) for compare/report progression text plus spinner states for execution generation
- route-specific delivery actions (PDF/email/presentation by current tab)
- usage dashboard with refresh states

Goal: reduce friction between generation, evaluation, and report delivery in one session.

---

## 13. Tradeoffs and Engineering Decisions

1. **PostgreSQL + SQLAlchemy + Alembic** over local-file SQLite and ad hoc DDL  
Why: production durability, a single portable access layer (ORM + pooling), reviewable schema evolution, and compatibility with App Runner plus **RDS PostgreSQL** (shared state across instances).  
Tradeoff: more infrastructure, explicit migration discipline, and operational attention to connection pooling and RDS connectivity (VPC connector, secrets).

2. Request-scope orchestration over background job queue  
Why: deterministic flow and simpler debugging.  
Tradeoff: long report/email operations stay request-bound.

3. Single container for UI + API  
Why: operational simplicity.  
Tradeoff: reduced independent scaling flexibility.

4. JSON artifact fields over fully normalized relational model  
Why: fast schema evolution for AI outputs.  
Tradeoff: more app-level validation and migration discipline required.

---

## 14. Challenges Solved During Implementation

1. Model output inconsistency  
Solution: strict validators + correction loops + deterministic fallbacks.

2. Cross-provider behavior differences  
Solution: provider-specific wrappers and ordered fallback policy.

3. Reproducible reporting from mutable saved data  
Solution: snapshot storage on rank reports.

4. Product UX under async latency  
Solution: loading skeletons, fixed footers, modal lock states, and explicit status messaging.

---

## 15. What This Project Demonstrates for AI Engineer Roles

This capstone demonstrates practical ability to:

1. Build full AI product systems, not only prototype prompts.
2. Design agentic workflows with deterministic orchestration.
3. Engineer reliability under provider and output instability.
4. Apply contract-first output governance for downstream safety.
5. Model **production-grade persistence**: PostgreSQL as the system of record, SQLAlchemy for typed access and pooling, Alembic for reviewable schema migrations, and RDS-aligned deployment assumptions.
6. Connect AI pipelines to production product UX and delivery channels.
7. Ship and operate a deployable stack with clear tradeoffs and roadmap.

---

## 16. Next Iteration Roadmap

1. Move report/email execution to async jobs with status polling.
2. Harden Postgres operations with backup drills, staging rehearsal, and richer migration checks.
3. Standardize API error envelope across all endpoints.
4. Add request correlation IDs across frontend, backend, and provider calls.
5. Add metrics for validation-failure rate, fallback rate, and per-endpoint latency.
6. Add offline evaluation harness for ranking and compare quality regression checks.

---

## 17. Resume-Ready Bullets

- Built an agentic multi-model AI platform (FastAPI + Next.js) that generates, ranks, compares, and summarizes business concepts into decision-ready artifacts.
- Implemented contract-first output validation, correction loops, and deterministic fallback behavior across generation and analysis agents to improve runtime reliability.
- Engineered multi-provider inference orchestration (OpenAI, Gemini, DeepSeek, Grok) with ordered fallback chains, token tracking, and plan-aware quota enforcement.
- Delivered report pipeline integration (HTML -> PDF via WeasyPrint, email via Resend) with saved artifact lifecycle and snapshot-backed reproducibility.
- Migrated persistence to **PostgreSQL** with **SQLAlchemy 2.x** models/sessions/pooling and **Alembic** migrations (**DDL before Uvicorn**; FastAPI `init_db()` only verifies connectivity), targeting **Amazon RDS** for production with **`DATABASE_URL_PROD` from AWS Secrets Manager**, plus JSONB-backed artifact storage and user-scoped access patterns.
- Designed and shipped full-stack user workflows for saved results, compare insights, and decision summary reporting with production-oriented guardrails.

---

## 18. Interview Walkthrough Script (5-7 Minutes)

1. Problem framing: why generation-only tools are insufficient for decision workflows.
2. Architecture overview: orchestrator-worker model and provider integration.
3. Reliability deep dive: validation, retries, fallbacks, and caching.
4. Data layer: PostgreSQL as system of record, SQLAlchemy session/pool model, **Alembic before Uvicorn** vs **`init_db()` connectivity-only** at FastAPI startup, JSONB artifacts vs normalized core tables.
5. Feature deep dive: compare and decision-report pipelines.
6. Tradeoffs and roadmap: what is production-ready today and what scales next.

---

## 19. AWS Deployment (ECR, App Runner, RDS, Secrets Manager)

This project is designed to run in AWS with a containerized deployment flow. **Two managed services are especially important to call out in interviews:** **Amazon RDS** holds all durable application data, and **AWS Secrets Manager** is the intended store for sensitive runtime configuration (database URL and API keys) that **App Runner** injects into the container—so secrets are not baked into the image.

```text
Local build
  -> Docker image
  -> Push to Amazon ECR
  -> App Runner service pulls image
  -> App Runner runs FastAPI container on port 8000
        -> reads env from plain config + Secrets Manager references (production)
        -> DATABASE_URL_PROD -> Amazon RDS for PostgreSQL (via VPC connector / private subnets)
  -> Health check: /health
```

### 19.1 Amazon RDS and AWS Secrets Manager (highlight)

**Amazon RDS for PostgreSQL**

- RDS is the **production system of record**: quotas, saved runs, comparisons, decision reports, execution plans—all persist in Postgres on RDS, not on the App Runner instance disk.
- The documented Terraform layout places RDS in **private subnets**; the App Runner service reaches it through **private VPC egress** (VPC connector), which matches how you would explain “database not on the public internet” in a capstone review.
- **Alembic** still runs inside the container at startup (`scripts/start_server.sh`); the migration target is whatever host/credentials **`DATABASE_URL_PROD`** points at—**in production that URL should resolve to the RDS endpoint**.

**AWS Secrets Manager**

- Terraform defines application secrets (see `terraform/secrets.tf`), including a dedicated secret for **`DATABASE_URL_PROD`** (naming pattern like `{prefix}/app/DATABASE_URL_PROD`) and separate secrets for LLM and email API keys.
- **App Runner** is configured to expose those values to the container as **environment variables** (secret references), so the Python app continues to use `os.getenv` / `DATABASE_URL_PROD` without embedding credentials in the image or repo.
- **Interview framing**: “RDS for durable state + Secrets Manager for credential injection + App Runner for compute” is a standard small-SaaS pattern on AWS.

Supporting pieces (also Terraform-backed in this repo): **Amazon ECR** for images, **AWS App Runner** for the service, optional **Route 53** for the custom domain, and **IAM** least-privilege wiring between services.

### 19.2 Deployment Steps

1. Authenticate Docker to ECR.
2. Build the container image using build args for Clerk public config.
3. Tag and push the image to ECR.
4. Create or update an App Runner service from that ECR image.
5. Configure runtime environment variables in App Runner.
6. Set health check path to `/health`.
7. Deploy and verify API plus static app routes.

### 19.3 Build and Push Commands

```bash
aws ecr get-login-password --region $DEFAULT_AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$DEFAULT_AWS_REGION.amazonaws.com

docker build --platform linux/amd64 \
  --build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY" \
  --build-arg NEXT_PUBLIC_CLERK_JWT_TEMPLATE="$NEXT_PUBLIC_CLERK_JWT_TEMPLATE" \
  -t ideagen-app .

docker tag ideagen-app:latest $AWS_ACCOUNT_ID.dkr.ecr.$DEFAULT_AWS_REGION.amazonaws.com/ideagen-app:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$DEFAULT_AWS_REGION.amazonaws.com/ideagen-app:latest
```

### 19.4 App Runner Runtime Configuration

Container settings:

- Port: `8000`
- Health endpoint: `/health`
- Auto deploy from ECR image: enabled (recommended)
- Custom domain: `ideagen.agentairg.site` (Route 53 mapping)

Environment variables to configure in App Runner:

- **`APP_ENV=prod`** (required so the app selects `DATABASE_URL_PROD`; see `api/config.py`)
- **`DATABASE_URL_PROD`** — **reference an AWS Secrets Manager secret** in production (full JDBC-style URL to RDS). Do not commit this value to git.
- `CLERK_JWKS_URL`
- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `GEMINI_API_URL`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_API_URL`
- `GROK_API_KEY`
- `GROK_API_URL`
- `RESEND_API_KEY`
- `EMAIL_FROM` (optional override)
- `ALLOWED_HOSTS` (recommended: `ideagen.agentairg.site`)
- `TOKEN_LIMIT_FREE` (optional)
- `TOKEN_LIMIT_PREMIUM` (optional)
- `SAVED_RESULTS_LIMIT_FREE_BYTES` (optional)
- `SAVED_RESULTS_LIMIT_PREMIUM_BYTES` (optional)

In production, treat **`DATABASE_URL_PROD`** and provider keys as **Secrets Manager**–backed references in App Runner rather than plaintext console entry where possible.

### 19.5 Custom Domain Setup (Route 53 + App Runner)

Implemented target:

- `ideagen.agentairg.site`

Implementation sequence:

1. In App Runner service, open `Custom domains` and link domain.
2. Select hosted zone `agentairg.site` in Route 53.
3. Use subdomain `ideagen`.
4. Use `CNAME` for subdomain mapping.
5. Wait for App Runner custom domain status to become `Active`.

Validation commands:

```bash
dig ideagen.agentairg.site +short
curl -I https://ideagen.agentairg.site
```

### 19.6 Restricting Access to Canonical Domain

To prevent normal app access via the default App Runner URL (`*.awsapprunner.com`), host allowlist middleware is used.

Behavior:

- Allowed hosts are controlled by `ALLOWED_HOSTS`.
- Requests from non-allowed hosts return `403`.
- `/health` remains accessible to preserve App Runner health checks.

Production recommendation:

```bash
ALLOWED_HOSTS=ideagen.agentairg.site
```

### 19.7 Data Persistence Model

Runtime persistence is **PostgreSQL** accessed only through **SQLAlchemy** (see **§10** for the application narrative; **`ARCHITECTURE.md` §6** for connection and migration detail). Tables cover usage metering, saved generation runs, comparisons, decision reports, and execution plans (`saved_stakeholder_reports`).

Production target (aligned with **§19.1**):

- **Amazon RDS for PostgreSQL** in private subnets (managed backups/patching path via AWS)
- **App Runner** private egress through a **VPC connector** to reach RDS
- **`DATABASE_URL_PROD`** supplied from **AWS Secrets Manager** into the container environment
- Schema upgrades via **Alembic** at container start (`scripts/start_server.sh`)

Practical implication:

- data is not tied to the container filesystem
- schema updates are **version-controlled revisions**, not opaque image state
- multiple App Runner instances share one **RDS** backend with pooled SQLAlchemy connections

### 19.8 AWS-Ready Strengths in Current Design

- Single-container deploy simplicity (frontend + API together)
- Health endpoint and Docker healthcheck built in
- **RDS + Secrets Manager** as first-class production pattern for data durability and credential handling
- No hardcoded cloud dependencies in application logic (URLs and keys from environment / secrets)

### 19.9 AWS Hardening Next Steps

1. Add centralized logging/metrics dashboards (CloudWatch).
2. Add structured request IDs for traceability across provider calls.
3. Add staged environments (dev/staging/prod) with separate ECR tags and App Runner services where quotas allow.
4. Add stronger rollback rehearsal and database restore drills.
5. Add CI/CD pipeline hardening for deploy approvals and post-deploy smoke tests.

---

## 20. Key File References

- `api/index.py` (FastAPI app; startup calls `db.init_db()` for **database connectivity check only**)
- `api/config.py` (database URL and pool settings)
- `api/database/models.py` (SQLAlchemy ORM tables)
- `api/database/session.py` (engine, session factory, `session_scope`)
- `api/db.py` (persistence helpers used by routes)
- `alembic.ini`, `alembic/env.py`, `alembic/versions/*.py`
- `scripts/start_server.sh` (Alembic then Uvicorn)
- `api/agent/idea_generation_agent.py`
- `api/agent/model_fallback.py`
- `api/agent/rank_result_agent.py`
- `api/agent/compare_results_agent.py`
- `api/agent/rank_report_agent.py`
- `api/agent/recommend_combination_agent.py`
- `api/agent/email_agent.py`
- `api/utils/pdf_utils.py`
- `pages/product.tsx`
- `Dockerfile`
- `next.config.ts`
- `ARCHITECTURE.md` (full system design; **§6** = persistence: PostgreSQL, SQLAlchemy, Alembic)
