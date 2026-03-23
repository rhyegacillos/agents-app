# IdeaGen Architecture (Implementation Reference)

This document describes the architecture that is **actually implemented** in this repository (`ideagen-saas-aws`), based on the current source code.

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


It is intentionally detailed and code-aligned, and is written as a technical reference for engineering, debugging, onboarding, and production hardening.

---

## 0) Agentic Framework Architecture (Implemented)

IdeaGen uses an **API-orchestrated agentic pattern**:

- FastAPI is the control plane and request coordinator.
- Agent modules are specialized inference workflows, each scoped to one feature domain.
- Validation, retries, and deterministic fallback behaviors are embedded per agent.
- There is no autonomous background planning loop and no inter-agent message bus.

This gives strong determinism and debuggability at the cost of lower decoupling than queue-based systems.

### 0.1 Core agentic primitives in this codebase

The implemented pattern combines:

1. Provider wrappers (`generate_openai_compatible`, `generate_gemini`) in `api/index.py`
2. Chain fallback runtime (`generate_with_fallback`) in `api/agent/model_fallback.py`
3. Output validation loops in each feature agent:
   - `idea_generation_agent.py` (HTML contract)
   - `rank_result_agent.py` (JSON contract)
   - `compare_results_agent.py` (JSON contract)
   - `rank_report_agent.py` (JSON contract)
   - `recommend_combination_agent.py` (strict exact-match + HTML contract)
4. Request-level orchestration in endpoint handlers in `api/index.py`

### 0.2 Agent topology by feature

There are six functional agent modules and one fallback runtime module:

- `idea_generation_agent.py`
  - Generates idea output in semantic HTML.
  - Applies validation/retry and delegates provider fallback to `model_fallback.py`.

- `rank_result_agent.py`
  - Scores/ranks outputs from a single multi-model run.
  - Enforces a rigid JSON response contract.

- `compare_results_agent.py`
  - Compares top-ranked output of Run A vs Run B.
  - Produces winner, rationale, key changes, risks, and decision memo.

- `rank_report_agent.py`
  - Produces multi-run decision summary and ranking.
  - Adds email-ready summary payload.

- `recommend_combination_agent.py`
  - Selects persona + 1-2 constraints from **allowed lists only**.
  - Enforces exact-string selection semantics.

- `email_agent.py`
  - Uses tool-calling to create email payload + audit metadata.
  - Sends via Resend and returns send status.

- `model_fallback.py`
  - Shared fallback policy engine used by generation agent.

### 0.3 Why this architecture is used here

This implementation chooses **request-scoped orchestration** rather than long-running agent graphs because:

- product actions are user-triggered and synchronous from UI,
- feature scope is bounded and naturally endpoint-oriented,
- reliability can be achieved with local retry/fallback contracts,
- deployment remains simple (single container app runtime with managed PostgreSQL persistence).

### 0.4 Cross-agent reliability contract

Across agents, the platform applies consistent reliability rules:

- **Validate outputs** against expected shape/content.
- **Retry with correction feedback** when validation fails.
- **Fallback safely** when retries are exhausted.
- **Track token usage** when provider usage metadata is available.
- **Avoid hidden assumptions** via prompt rules (explicitly stated in system/user prompts).

### 0.5 Control-plane boundaries

What FastAPI controls:

- Authentication and user identity resolution.
- Premium gating and quota checks.
- Model/provider routing.
- Orchestration ordering (generate -> rank -> persist, etc.).
- Artifact persistence and retrieval.
- PDF rendering and email dispatch.

What agents control:

- Prompted reasoning for task-specific analysis.
- Local schema-format output.
- Task-level fallback payload generation.

### 0.6 Demonstration: Core Agentic AI Development Patterns

This section maps core Agentic AI development patterns to the exact implementation in this project.

#### Pattern A: Orchestrator-Worker (API as control plane, agents as workers)

Intent:

- Keep business workflow deterministic in a central orchestrator.
- Delegate reasoning-heavy subtasks to specialized worker agents.

Where implemented:

- Orchestrator: endpoint handlers in `api/index.py`
- Workers: `api/agent/*.py`

Concrete demonstration:

1. `POST /api` orchestrates request parsing, gating, model fan-out, usage aggregation, and ranking trigger.
2. `generate_idea_agentic` performs worker-level generation and validation loop.
3. `rank_result_agent` is called as a second worker only when multi-model outputs exist.

Reusable pattern template:

```text
Controller receives request
  -> validates/gates
  -> dispatches specialized workers
  -> merges worker outputs
  -> persists + returns normalized response
```

#### Pattern B: Contract-First Agent Outputs

Intent:

- Treat each agent output as a machine-consumable contract, not free-form text.

Where implemented:

- HTML contract: `api/agent/idea_generation_agent.py`
- JSON contracts:
  - `api/agent/rank_result_agent.py`
  - `api/agent/compare_results_agent.py`
  - `api/agent/rank_report_agent.py`
  - `api/agent/recommend_combination_agent.py`

Concrete demonstration:

- Generation agent rejects fenced markdown and too-short output.
- Ranking/comparison/report agents validate required keys, list lengths, and ID coverage.
- Recommend agent enforces exact-string selection from allowed values plus `reason_html` wrapper shape.

Reusable pattern template:

```text
LLM call
  -> parse output
  -> validate against strict contract
  -> accept only if contract is satisfied
```

#### Pattern C: Self-Correction Retry Loop (validator-in-the-loop)

Intent:

- Let the same agent self-correct by feeding validation errors back as actionable constraints.

Where implemented:

- `generate_idea_agentic` (`max_attempts=3`)
- `rank_result_agent` (`max_attempts=2`)
- `compare_results_agent` (`max_attempts=2`)
- `rank_report_agent` (`max_attempts=2`)
- `recommend_combination_agent` (`max_attempts=3`)

Concrete demonstration:

- On validation failure, agents append a correction block:
  - "VALIDATION ERRORS FROM YOUR LAST OUTPUT..."
- Next attempt must return corrected output only.

Reusable pattern template:

```text
for attempt in N:
  output = call_model(prompt + correction_feedback)
  if validate(output): return output
  correction_feedback = build_errors(validate_errors)
return deterministic_fallback()
```

#### Pattern D: Multi-Provider Routing + Ordered Fallback

Intent:

- Increase reliability by routing to provider-specific chains and failing over on transient errors.

Where implemented:

- Routing map: `FALLBACK_CHAINS` in `api/index.py`
- Fallback engine: `generate_with_fallback` in `api/agent/model_fallback.py`

Concrete demonstration:

- Provider inferred from model prefix or resolved from chain.
- Transient non-timeout failures trigger fallback to next model.
- Timeout errors do not silently switch provider; caller retry logic handles timeout separately.

Reusable pattern template:

```text
for model in ordered_chain:
  try call(model)
  except timeout: raise_for_retry_same_context
  except transient: continue_to_next_model
  except hard_error: raise
```

#### Pattern E: Progressive Analysis Pipelines (compose agents by stage)

Intent:

- Build higher-value outputs by chaining specialized analysis stages.

Where implemented:

- Generation pipeline (`/api`): generate -> rank -> finalize labels/titles
- Compare pipeline (`/api/compare-results`): ensure rank -> pick top outputs -> compare
- Decision pipeline (`/api/rank-report`): resolve run set -> report agent -> delivery (pdf/email)

Concrete demonstration:

- Compare path computes missing rank data before comparison.
- Decision path reuses cached report when available, otherwise runs report agent.

Reusable pattern template:

```text
stage_1 artifact -> stage_2 enrichment -> stage_3 decision artifact
```

#### Pattern F: Cache-Before-Infer

Intent:

- Avoid repeated expensive inference for identical artifact requests.

Where implemented:

- Comparison cache: `db.get_saved_comparison(...)`
- Report cache: `db.get_saved_rank_report(...)` keyed by sorted `run_ids_key`

Concrete demonstration:

- Same run pair returns cached comparison.
- Same run-set key returns cached decision report.
- If cached artifacts are partially missing fields (e.g., top outputs), runtime backfills from source rows.

Reusable pattern template:

```text
lookup(cache_key)
if hit: return cached_or_backfilled
else: infer -> persist -> return
```

#### Pattern G: Deterministic Safety Fallbacks

Intent:

- Ensure feature continuity even when model output quality/availability fails.

Where implemented:

- `_fallback_ranking` in `rank_result_agent.py`
- `_fallback_comparison` in `compare_results_agent.py`
- `_fallback_report` in `rank_report_agent.py`
- deterministic first-option fallback in `recommend_combination_agent.py`
- fallback email payload in `email_agent.py`

Concrete demonstration:

- System returns usable, explicit fallback payloads instead of empty responses or hard crashes.
- Fallback text marks reduced-confidence output clearly for user/operator awareness.

#### Pattern H: Tool-Calling for Side Effects (email as controlled action)

Intent:

- Keep side effects explicit and auditable through tool contracts.

Where implemented:

- `api/agent/email_agent.py` with tools:
  - `send_email`
  - `log_action`

Concrete demonstration:

- Prompt enforces exactly one send tool call and one log tool call.
- Structured audit metadata is captured before dispatching via Resend.

Reusable pattern template:

```text
LLM plans message -> emits structured tool args -> runtime executes external side effect
```

#### Pattern I: Guardrails at Multiple Layers

Intent:

- Prevent misuse and cost blowups with layered guardrails beyond prompt instructions.

Where implemented:

- Auth guard: Clerk JWT verification (`CustomClerkHTTPBearer`)
- Plan guard: premium checks (`require_premium`)
- Quota guards: API/token/email/storage checks in `api/db.py` and endpoints
- UI guardrails: disabled states, premium locks, limit notices in `pages/product.tsx`

Concrete demonstration:

- Recommend endpoint is premium-gated server-side even if UI is bypassed.
- Save endpoint blocks writes when storage cap is exceeded.
- Compare/report generation is blocked when token quota is reached.

#### Pattern J: State Snapshotting for Durable Report Reproducibility

Intent:

- Keep generated report artifacts renderable even if source records later change or are deleted.

Where implemented:

- `runs_json` snapshot stored in `saved_rank_reports`.

Concrete demonstration:

- PDF generation for saved rank report first uses snapshot; only reconstructs from IDs if snapshot missing.
- Missing reconstruction is surfaced via response header (`X-Report-Runs-Missing`).

#### Practical takeaway from these patterns

The project demonstrates a production-lean agentic style:

- centralized deterministic orchestration,
- strict output contracts and correction loops,
- explicit fallback and caching strategies,
- controlled external side effects,
- layered guardrails tied to billing and auth boundaries.

---

## 1) High-Level System Context

### 1.1 Top-level architecture

```text
Browser (Next.js static export)
  |
  | Bearer JWT (Clerk template token)
  v
FastAPI (api/index.py)
  |-- Custom Clerk JWT verify (JWKS + PyJWT)
  |-- Plan & quota checks (api/db.py -> SQLAlchemy session)
  |-- Agent orchestration (api/agent/*.py)
  |-- PDF rendering (api/utils/pdf_utils.py + WeasyPrint)
  |-- Email delivery (api/agent/email_agent.py -> Resend)
  |
  +--> PostgreSQL via SQLAlchemy (api/database/session.py, models in api/database/models.py; schema via Alembic)
  +--> OpenAI / Gemini / DeepSeek / Grok APIs
```

**AWS production (reference deployment):** the container image lives in **Amazon ECR** and runs on **AWS App Runner**. Durable data lives in **Amazon RDS for PostgreSQL** (private subnets; App Runner reaches RDS via **VPC connector** / private egress). Sensitive runtime values—especially **`DATABASE_URL_PROD`** and API keys—are intended to live in **AWS Secrets Manager** and be **referenced into App Runner** as environment variables (see `terraform/secrets.tf`), not committed to the repository or baked into the image.

### 1.2 Runtime boundaries

- Frontend is built as static assets (`next export`) and served by FastAPI at root path.
- Backend API remains dynamic under `/api/*`.
- Authentication is enforced only on protected API routes (not on static assets).
- Data persistence is PostgreSQL-backed; local dev uses Docker Compose Postgres; **AWS** production uses **Amazon RDS** with **`DATABASE_URL_PROD`** typically sourced from **AWS Secrets Manager** and injected into **App Runner**.

### 1.3 Capability map

Implemented product capabilities:

1. Generate multi-model idea outputs for one configuration.
2. Rank model outputs inside a run.
3. Auto-save generated runs and reload/delete them.
4. Compare two runs (same-config constraint) and cache comparison.
5. Generate decision summary report across selected runs.
6. Export generated/compare/rank-report PDFs.
7. Email generated/compare/rank-report artifacts.
8. Premium-only recommendation of persona + constraints.

### 1.4 Non-goals (current implementation)

Not implemented in current architecture:

- asynchronous job queue for long-running tasks,
- read replicas, automated failover drills, or multi-region database topology as first-class architecture (single primary PostgreSQL / RDS is the current target),
- event-driven or pub/sub orchestration,
- distributed tracing and metrics backend,
- strict global response error schema contract.

---

## 2) Deployment Topology and Runtime Packaging

### 2.1 Container build pipeline

`Dockerfile` uses two stages:

1. **Frontend builder** (`node:22-alpine`)
   - installs npm dependencies via `npm ci`
   - runs `npm run build`
   - emits static files in `/app/out`

2. **Python runtime** (`python:3.12-slim`)
   - installs system deps required by WeasyPrint stack
   - installs Python dependencies from `requirements.txt`
   - copies backend (`api/`) and aliases `api/index.py` as `server.py`
   - copies static export from stage 1 into `/app/static`
   - runs uvicorn (`server:app`) on port `8000`

### 2.2 Process model

- Single uvicorn process serves:
  - API routes (`/api/*`, `/health`)
  - static frontend routes (`/` and exported files)
- No sidecar services required for baseline runtime.

### 2.3 Static hosting behavior

Next.js config:

- `output: "export"`
- `trailingSlash: true`

FastAPI static mount:

- `app.mount("/", StaticFiles(directory="static", html=True), name="static")`

Implication:

- Paths depend on exported static path structure, so trailing slash behavior matters.
- Refresh behavior differs from SSR apps because this is static export + static serving.

### 2.4 Runtime ports and health

- Service port: `8000`
- Health endpoint: `GET /health`
- Docker healthcheck calls `http://localhost:8000/health`

### 2.5 Persistent data paths

- No application database file path is used in the current architecture.
- Persistence is externalized to PostgreSQL.
- Local development uses `DATABASE_URL_LOCAL`; AWS deploys use `DATABASE_URL_PROD`.

### 2.6 Environment variable matrix

Backend/auth:

- `CLERK_JWKS_URL`

Database (PostgreSQL via SQLAlchemy; see **§6**):

- `APP_ENV` — `local` or `prod` (selects which URL is active; see `api/config.py`)
- `DATABASE_URL_LOCAL` — required when `APP_ENV=local` (typical local form: `postgresql+psycopg://user:pass@host:5432/dbname`)
- `DATABASE_URL_PROD` — required when `APP_ENV=prod`; in **AWS**, this should be the SQLAlchemy URL to **Amazon RDS** (see **§2.7**), injected via **AWS Secrets Manager** into **App Runner** (Terraform: `aws_secretsmanager_secret.database_url_prod` and service configuration—not checked into git)

LLM providers:

- `OPENAI_API_KEY`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_API_URL`
- `GROK_API_KEY`
- `GROK_API_URL`
- `GEMINI_API_KEY`
- `GEMINI_API_URL`

Email:

- `RESEND_API_KEY`
- `EMAIL_FROM` (optional, default no-reply format)

Usage/storage limits:

- `TOKEN_LIMIT_FREE` (default 50000)
- `TOKEN_LIMIT_PREMIUM` (default 500000)
- `SAVED_RESULTS_LIMIT_FREE_BYTES` (default 100MB)
- `SAVED_RESULTS_LIMIT_PREMIUM_BYTES` (default 1GB)
- `DB_POOL_SIZE` (optional override)
- `DB_MAX_OVERFLOW` (optional override)
- `DB_POOL_TIMEOUT` (optional override)
- `DB_POOL_RECYCLE` (optional override)
- `DB_ECHO` (optional override)

Frontend env used in UI behavior:

- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
- `NEXT_PUBLIC_CLERK_JWT_TEMPLATE`
- `NEXT_PUBLIC_TOKEN_LIMIT_FREE`
- `NEXT_PUBLIC_TOKEN_LIMIT_PREMIUM`

### 2.7 AWS services in the reference deployment (RDS + Secrets Manager)

This repository’s **Terraform** stack models a small-SaaS shape on AWS. The following services are the ones worth naming explicitly when explaining deployment:

| AWS service | Role in this design |
|-------------|---------------------|
| **Amazon ECR** | Stores the built **Docker** image; App Runner pulls from here (often with automatic deploy on push). |
| **AWS App Runner** | Runs the **FastAPI** + static frontend container on port **8000**; maps **Secrets Manager** secrets and plain env vars into the task environment. |
| **Amazon RDS for PostgreSQL** | **System of record** for all application tables (usage, saved artifacts, reports). Placed in **private subnets** in the Terraform layout; not dependent on ephemeral container disk. |
| **AWS Secrets Manager** | Holds **`DATABASE_URL_PROD`** (full connection string to RDS) and provider keys (OpenAI, Gemini, DeepSeek, Grok, Resend, etc.) under names like `{prefix}/app/DATABASE_URL_PROD` — see `terraform/secrets.tf`. App Runner is configured to expose these as **environment variables** to the app. |
| **VPC / VPC connector** | Lets App Runner use **private** egress to reach **RDS** without exposing the database to the public internet. |
| **Route 53** (optional) | Custom domain (e.g. `ideagen.agentairg.site`) in front of App Runner. |
| **IAM** | Least-privilege roles for App Runner to read secrets, pull from ECR, and (where configured) manage related resources. |

**Application contract:** the Python code still reads **`DATABASE_URL_PROD`** and API keys from the process environment (`api/config.py`, standard `os.getenv` paths). The **AWS** responsibility is to populate those variables from **Secrets Manager** at runtime—not to change application code per cloud.

---

## 3) Codebase Responsibility Map

### 3.1 Frontend layers

- `pages/_app.tsx`
  - wraps app in Clerk provider.

- `pages/index.tsx`
  - landing/marketing shell.
  - auth-aware entry to product page.

- `pages/product.tsx`
  - core product workspace.
  - UI state machine for generation, saved artifacts, compare, decision report.
  - modal orchestration and draggable saved-panel behavior.
  - all API integrations from browser.

### 3.2 Backend layers

- `api/index.py`
  - FastAPI app lifecycle.
  - authentication and plan gating.
  - all endpoint orchestration.
  - model provider wrapper calls.

- `api/config.py`
  - resolves `APP_ENV` and a single effective `database_url` plus pool tuning settings.

- `api/database/models.py`
  - SQLAlchemy 2.x declarative ORM definitions (tables, columns, JSONB, indexes, check constraints).

- `api/database/session.py`
  - engine creation, connection pool, `sessionmaker`, `session_scope`, `verify_database_connection`.

- `api/db.py`
  - persistence helpers used by routes: usage counters and limit checks, CRUD for saved runs/comparisons/reports/execution plans.
  - `init_db()` verifies DB connectivity only; **schema is not created here** (Alembic owns DDL).

- `alembic/`
  - versioned schema migrations applied with `alembic upgrade head` (container entry runs this before Uvicorn when a DB URL is set).

- `api/agent/*.py`
  - feature-specific agentic workflows.

- `api/utils/pdf_utils.py`
  - HTML templating for all PDF artifact types.
  - WeasyPrint conversion.

- `api/instructions/instructions_prompt.py`
  - generation prompt contracts (system/user prompt scaffolds).

### 3.3 Supporting technical docs in repo

- `technical_backend.md`
- `agentic_architecture.md`
- `api_reference.md`
- `data_model.md`
- `billing_limits.md`
- `deployment_runbook.md`

These are supporting docs; source-of-truth behavior remains the runtime code.

---

## 4) Detailed Backend Architecture (`api/index.py`)

### 4.1 App bootstrap and logging

- `load_dotenv()` loads env values.
- `app = FastAPI()` initializes app.
- `startup_event()` runs `db.init_db()`, which **only verifies** database connectivity (`SELECT 1`). Table creation and DDL changes are applied by **Alembic** before the process starts in the supported Docker/deploy path (`scripts/start_server.sh`).
- logging is configured with `force=True`, INFO level, and noisy libraries are muted.

### 4.2 Authentication architecture

Auth is implemented via `CustomClerkHTTPBearer`:

1. Read `Authorization` header.
2. Extract bearer token.
3. Resolve signing key via `PyJWKClient` and Clerk JWKS URL.
4. Decode token using RS256 with:
   - `leeway=120`
   - `verify_aud=False`
5. Attach decoded payload to credentials object (`creds.decoded`).
6. Raise `403` on any verification failure.

This is a manual verification path replacing default strict middleware behavior.

### 4.3 Provider clients and model IDs

Configured clients:

- `openai_client` (OpenAI)
- `deepseek_client` (OpenAI-compatible endpoint)
- `grok_client` (OpenAI-compatible endpoint)
- `google_client` (OpenAI-compatible Gemini endpoint)
- `gemini_client` (Google GenAI native SDK path)

Primary model constants:

- OpenAI: `gpt-5-mini`
- Gemini: `gemini-2.5-pro`
- DeepSeek: `deepseek-chat`
- Grok: `grok-4-1-fast-reasoning`

Fallback model constants also exist per provider.

### 4.4 Fallback chain map

`FALLBACK_CHAINS` maps each primary model to:

- provider name (`openai`, `gemini`, `deepseek`, `grok`)
- ordered model chain list `[primary, fallback]`

This is consumed by generation orchestration and agent-level fallback runtime.

### 4.5 Request and response schemas (Pydantic)

Core request models include:

- `IdeaRequest`
- `ReportData`
- `EmailRequest`
- `SaveResultsRequest`
- `CompareResultsRequest`
- `RankReportRequest`
- `RecommendCombinationRequest`

Response model with explicit typing:

- `RecommendCombinationResponse`

### 4.6 Utility functions in `index.py`

Key helpers:

- filename builders (`build_pdf_filename`, `build_rank_report_filename`, `build_compare_report_filename`)
- title extraction (`extract_result_title`)
- ranking cleanup (`sanitize_rank_text`, `finalize_rank_result`)
- email brief construction (`build_rank_report_email_brief`, `build_idea_report_email_brief`, etc.)
- JSON parsing helper (`_extract_json_object`)
- plan gating helpers (`get_user_plan`, `is_premium`, `require_premium`)

### 4.7 Provider wrapper behavior

`generate_openai_compatible(...)`:

- Calls chat completions API with `temperature` and `top_p`.
- If model rejects sampling params, retries without custom params.
- Returns `(text, usage)` with usage token counters when present.

`generate_gemini(...)`:

- Calls Gemini native SDK with config.
- On 429/resource exhaustion, attempts fallback Gemini model.
- Returns `(text, usage)` or error-formatted fallback.

### 4.8 Premium and storage gate constants

- `PREMIUM_PLANS` contains accepted premium plan strings.
- Saved result storage limit byte caps are plan-dependent.

---

## 5) API Surface and Request Semantics

All protected routes expect Clerk bearer auth unless explicitly public (`/health`).

### 5.1 `GET /api/subscription`

Purpose:

- sync/create user usage row,
- return plan + usage snapshot.

Behavior:

1. Resolve `user_id` (`sub`) and `plan` (`pla`) from token.
2. Ensure user row exists and plan sync is applied.
3. Return usage stats from DB.

### 5.2 `POST /api/saved-results`

Purpose:

- persist generated run artifacts.

Behavior:

1. Validate `results` is non-empty.
2. Compute current storage bytes for user.
3. Estimate payload byte size.
4. Enforce plan-based storage cap.
5. Persist run row with JSON fields.

Failure modes:

- `400` no results.
- `413` storage cap exceeded.

### 5.3 `GET /api/saved-results`

Purpose:

- list saved runs + storage usage meter values.

Behavior:

- returns limited list, usage bytes, limit bytes.

### 5.4 `GET /api/saved-results/{saved_id}`

Purpose:

- fetch one saved run scoped to current user.

Failure:

- `404` not found.

### 5.5 `DELETE /api/saved-results/{saved_id}`

Purpose:

- delete one saved run scoped to current user.

Failure:

- `404` not found.

### 5.5a `DELETE /api/saved-results`

Purpose:

- bulk-delete all saved generated runs scoped to current user.

Behavior:

- deletes all rows in `saved_results` for the authenticated user,
- returns deleted row count in response payload.

Response:

- `{ "status": "deleted", "count": <int> }`

### 5.6 `POST /api/compare-results`

Purpose:

- compare two saved runs and produce diff insight.

Detailed flow:

1. Token limit check (`check_token_limit`).
2. Ensure run IDs are distinct.
3. Load both runs, user-scoped.
4. Validate normalized config equality:
   - industry
   - persona
   - constraints set (normalized)
   - models set (normalized)
5. Check cached comparison (`get_saved_comparison`).
6. If cached exists but missing top outputs, backfill top outputs from runs.
7. For non-cached path:
   - ensure per-run ranking exists (`ensure_rank_result_for_run`)
   - rank on-demand for multi-model runs if missing
   - persist rank result back to saved run
   - select top output per run
   - call `compare_results_agent`
8. Attach `top_outputs` payload to comparison.
9. Derive `winner_run_id` from winner label.
10. Save comparison row.
11. Track token usage if provided.
12. Return comparison payload with `cached` flag.

Failure modes:

- `429` token limit reached
- `400` same run or mismatched config
- `404` run not found

### 5.7 `GET /api/compare-results`

Purpose:

- list saved comparisons for user.

### 5.8 `DELETE /api/compare-results/{comparison_id}`

Purpose:

- delete saved comparison.

### 5.8a `DELETE /api/compare-results`

Purpose:

- bulk-delete all saved comparisons for current user.

Behavior:

- removes all rows from `saved_comparisons` scoped by `user_id`,
- returns deleted count for UI toast/status consistency.

### 5.9 `GET /api/compare-results/{comparison_id}/pdf`

Purpose:

- render compare result PDF.

Behavior details:

1. Load saved comparison.
2. If `top_outputs` are missing in stored blob, reconstruct from referenced runs.
3. Build compare report HTML via `create_compare_report_html`.
4. Convert HTML to PDF bytes.
5. Return streaming response with filename header.

### 5.10 `POST /api/compare-results/{comparison_id}/email`

Purpose:

- email compare report PDF.

Behavior:

1. Check/increment email quota.
2. Load saved comparison.
3. Backfill top outputs if missing.
4. Build compare PDF.
5. Build compare-specific subject and brief.
6. Call centralized `send_report_email`.

Failures:

- `429` email quota
- `404` comparison not found
- `502` email delivery failure

### 5.11 `GET /api/rank-reports`

Purpose:

- list saved decision summary reports.

### 5.11a `DELETE /api/rank-reports`

Purpose:

- bulk-delete all saved decision summary reports for current user.

Behavior:

- removes all rows from `saved_rank_reports` for authenticated user,
- returns deleted count for UI feedback.

### 5.12 `GET /api/rank-reports/{report_id}`

Purpose:

- fetch one decision summary report payload.

### 5.13 `GET /api/rank-reports/{report_id}/pdf`

Purpose:

- render decision summary report PDF.

Behavior:

1. Load report row.
2. Prefer `runs_snapshot` if present.
3. Else reconstruct runs via `run_ids` lookup.
4. Render rank report HTML + PDF.
5. Return `X-Report-Runs-Missing: true` header when reconstructed set is incomplete.

### 5.14 `POST /api/rank-reports/{report_id}/email`

Purpose:

- email existing saved decision summary report.

Behavior:

1. Check/increment email quota.
2. Load report row.
3. Render PDF from snapshot + report payload.
4. Build report email context and call `send_report_email`.

Failures:

- `429` email quota
- `404` report not found
- `502` email send failure

### 5.15 `POST /api/rank-report`

Purpose:

- generate (or reuse cached) decision summary report for selected run set.

Detailed flow:

1. Token limit check.
2. Validate `output` mode (`pdf|email|both`).
3. Validate email requirement for `email|both`.
4. If email required, check/increment email quota.
5. Resolve run set:
   - selected run IDs (max 5), or
   - include all saved runs
6. Build deterministic `run_ids_key` from sorted IDs.
7. Lookup cached report by key.
8. On cache miss:
   - call `rank_report_agent`
   - track token usage
   - persist report + snapshot
9. Build PDF bytes regardless of output mode.
10. If email mode requested, send via `send_report_email`.
11. Return:
   - JSON status for `output=email`
   - PDF stream for `output=pdf|both`
   - response headers indicating cache/email outcomes.

### 5.16 `POST /api`

Purpose:

- primary generation endpoint.

Detailed flow:

1. Generate `request_id`.
2. Check/increment API call quota (also checks token monthly limit).
3. Build prompts:
   - system prompt from persona (`system_instructions`)
   - user prompt from industry + constraints (`user_instruction`)
4. Resolve requested model labels to model IDs:
   - UI sends labels (`OpenAI`, `Gemini`, etc.)
   - backend maps to primary model IDs via `FALLBACK_CHAINS`
5. For each model ID, run concurrent generation task (`asyncio.gather`):
   - infer provider
   - choose client + generate function
   - call `generate_idea_agentic`
6. Aggregate outputs and token usage.
7. Track generation token usage.
8. Build `title_map` and `label_map`.
9. If multi-model output, call `rank_result_agent` and finalize rank payload.
10. If single model, return rank skipped payload.
11. Return JSON: `results`, `usage`, `rank_result`.

### 5.17 `POST /api/download-pdf`

Purpose:

- generate PDF for current unsaved generated run payload.

Behavior:

- render HTML via `create_report_html`
- convert to PDF bytes
- stream with generated filename

### 5.18 `POST /api/email`

Purpose:

- email generated run report PDF (not saved-artifact specific).

Behavior:

1. Check/increment email quota.
2. Render PDF from request payload.
3. Build idea email brief.
4. Send via `send_report_email`.

### 5.19 `POST /api/recommend-combination`

Purpose:

- premium-only recommendation endpoint.

Behavior:

1. Enforce premium plan.
2. Check/increment API quota.
3. Call `recommend_combination_agent` with:
   - industry
   - allowed constraints
   - allowed personas
4. Track usage tokens if present.
5. Return recommended constraints/persona + `reason_html`.

### 5.20 `GET /health`

Purpose:

- health probe endpoint.

Returns:

- `{"status": "healthy"}`

### 5.21 Static mount order

`app.mount("/", StaticFiles(...))` is intentionally last so API routes resolve first.

---

## 6) Persistence Architecture (PostgreSQL, SQLAlchemy, Alembic)

Persistence is intentionally split across three concerns so the architecture stays understandable in reviews and interviews:

1. **PostgreSQL** — durable system of record (local Docker Compose in dev, **Amazon RDS for PostgreSQL** in the documented AWS path; **`DATABASE_URL_PROD`** supplied from **AWS Secrets Manager** into **App Runner** per **§2.7**). The database is never a file inside the container image.
2. **SQLAlchemy 2.x** — typed application access: declarative ORM models, a pooled engine, and short-lived sessions. Routes and agents do not embed raw SQL for routine CRUD; they call helpers in `api/db.py`.
3. **Alembic** — **exclusive** owner of schema creation and change. DDL is versioned, reviewable, and replayed with `alembic upgrade head`.

Together, these replace an older SQLite-in-container approach: multiple App Runner instances can share one database, JSON payloads use **JSONB**, and schema drift is handled with migrations instead of startup `ALTER TABLE` scripts.

### 6.1 How the pieces fit at runtime

```text
FastAPI request
  -> api/index.py (auth, orchestration)
  -> api/db.py (transactions + domain persistence helpers)
        -> session_scope() / Session
              -> SQLAlchemy ORM (api/database/models.py)
                    -> psycopg (SQLAlchemy URL: postgresql+psycopg://...)
                          -> PostgreSQL
```

**Read path:** `get_settings()` supplies `database_url`; `get_engine()` builds (once) a SQLAlchemy `Engine` with pooling; `sessionmaker` produces `Session` instances; `api/db.py` runs queries/updates inside `session_scope()` or explicit `session.begin()` blocks.

**Write path:** the same stack applies. User isolation is enforced in application logic by **always** scoping queries with `user_id` (and by never trusting client-supplied IDs without a user match).

**Schema path:** before Uvicorn accepts traffic in the standard container entrypoint, `scripts/start_server.sh` runs `alembic upgrade head` when `DATABASE_URL_LOCAL` or `DATABASE_URL_PROD` is set. FastAPI startup then calls `init_db()`, which only runs `verify_database_connection()` — a cheap sanity check that the pool can reach the server.

### 6.2 Configuration: one URL, explicit environment (`api/config.py`)

The backend does not discover the database implicitly. `get_settings()` (cached) enforces:

- `APP_ENV` is `local` or `prod` (with a heuristic default toward `prod` when AWS environment markers are present).
- `APP_ENV=local` requires **`DATABASE_URL_LOCAL`**.
- `APP_ENV=prod` requires **`DATABASE_URL_PROD`**.

Exactly **one** `database_url` is selected for the process. Documented examples use the SQLAlchemy v2 driver form **`postgresql+psycopg://...`** (Psycopg 3). Using the same dialect locally and in production avoids subtle semantic differences between SQLite and Postgres that used to hide behind ad hoc SQL.

Optional pool tuning (all read in `get_settings()`):

- `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE`, `DB_ECHO`

These map directly to `create_engine(...)` in `api/database/session.py`. **`pool_pre_ping`** is enabled so stale connections are discarded before they surface as random request failures after idle periods — important behind RDS and NAT.

### 6.3 Engine, pool, and session semantics (`api/database/session.py`)

- **`get_engine()`** — lazily constructs a single global `Engine` bound to `settings.database_url`, with `future=True` for SQLAlchemy 2.x behavior.
- **`get_session_factory()`** — `sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)`.
  - `autoflush=False` keeps flush timing explicit inside transaction boundaries.
  - `expire_on_commit=False` avoids surprise lazy reloads on committed instances when response serialization still touches ORM attributes.
- **`session_scope()`** — context manager: open session, `yield`, **always** `close()` in `finally` so connections return to the pool.
- **`verify_database_connection()`** — `SELECT 1`; used by `init_db()` at app startup.

No async SQLAlchemy stack is used in the current phase: the API remains synchronous end-to-end for DB I/O, which keeps the Postgres migration tractable and is sufficient while LLM latency dominates most routes.

### 6.4 Alembic: schema ownership and workflow

Files:

- `alembic.ini` — script location and logging hooks.
- `alembic/env.py` — binds metadata from the SQLAlchemy `Base`, loads `database_url` from application settings, runs migrations **offline** (SQL) or **online** (engine).
- `alembic/versions/*.py` — one revision per logical schema change (e.g. initial baseline creating all application tables).

**Rule:** new tables, columns, indexes, or constraints are added by **generating a new Alembic revision**, not by editing startup code in `api/db.py`. That rule is what makes schema changes auditable in pull requests and reproducible across environments.

**Deploy ordering:** `scripts/start_server.sh` runs `alembic upgrade head` first, then starts Uvicorn. If you run `uvicorn` directly on a laptop without that wrapper, you must run Alembic yourself once the database exists — otherwise the app will fail on missing tables even though `init_db()` “succeeds” (connectivity only).

**Optional one-time data path:** `scripts/import_sqlite_to_postgres.py` exists for migrating legacy SQLite dumps into Postgres. Normal operation reads and writes **only** through PostgreSQL.

### 6.5 ORM models and the persistence façade (`api/database/models.py`, `api/db.py`)

**Models** (`api/database/models.py`) define:

- table names and column types aligned with Postgres (`BigInteger` + `Identity()` for surrogate keys, `DateTime(timezone=True)` for timestamps, `JSONB` for structured blobs),
- **check constraints** (e.g. non-negative usage counters, allowed `source_type` values on stakeholder reports),
- **indexes** supporting common list and lookup patterns (`user_id` + `created_at`, compare pair + user, etc.).

Relationships between tables are **not** heavily normalized with ORM `relationship()` cascades: artifact graphs are intentionally **JSON-heavy** for fast iteration on LLM output shapes; referential integrity for “run A / run B” is enforced by application logic and typing, not by foreign keys to `saved_results` in the baseline schema.

**Persistence façade** (`api/db.py`) is what `api/index.py` imports. It:

- imports ORM classes from `database.models`,
- uses `session_scope`, `get_session`, and SQLAlchemy `select` / `update` / `delete` / `func` patterns,
- implements quota checks, saved artifact CRUD, caching lookups for reports and comparisons, and storage byte estimation for plan limits.

This layout keeps FastAPI routes thin: they authenticate, validate Pydantic payloads, and delegate storage rules to `db.*` functions.

### 6.6 Table reference (logical schema)

The following matches the ORM intent; authoritative DDL is in Alembic revisions.

#### `user_usage`

Purpose: per-user **plan** and **quota counters** (tokens, API window, emails).

Notable columns:

- `user_id` (`TEXT`, primary key)
- `plan` (`TEXT`)
- `total_tokens` (`BIGINT`, constrained non-negative)
- `api_calls_count`, `emails_sent_count` (`INTEGER`, constrained non-negative)
- `api_window_start` (`TIMESTAMPTZ`) — rolling window anchor for per-minute API limits
- `emails_last_sent_date` (`DATE`, nullable) — UTC date for daily email cap
- `tokens_last_reset_month` (`TEXT`, `YYYY-MM`) — month bucket for token totals
- `created_at`, `updated_at` (`TIMESTAMPTZ`)

#### `saved_results`

Purpose: **generated runs** (multi-model outputs + config).

Notable columns:

- `id` (`BIGINT`, Postgres `IDENTITY`, primary key)
- `user_id`, `created_at` (`TIMESTAMPTZ`)
- `industry`, `tone` (`TEXT`, nullable)
- `constraints_json`, `models_json`, `results_json`, `rank_result_json` (`JSONB`)

Indexes support listing by user ordered by time and keyed lookups by `(user_id, id)`.

#### `saved_rank_reports`

Purpose: **decision summary** artifacts with **snapshot** durability.

Notable columns:

- `id` (`BIGINT` identity PK), `user_id`, `created_at`
- `run_ids_key` (`TEXT`) — normalized cache key (sorted run ids)
- `run_ids_json`, `report_json`, `runs_json` (`JSONB`) — `runs_json` stores snapshot payloads for reproducible PDF/email even if source runs change
- `model` (`TEXT`, nullable)

#### `saved_comparisons`

Purpose: **compare** artifacts for a run pair.

Notable columns:

- `id` (identity PK), `user_id`, `created_at`
- `run_a_id`, `run_b_id`, `winner_run_id` (`BIGINT`)
- `comparison_json` (`JSONB`), `model` (`TEXT`, nullable)

Indexes support “latest comparison for this user + pair” query patterns.

#### `saved_stakeholder_reports`

Purpose: **Execution Plan** / stakeholder dossiers (Grounded Finance v2 and related metadata).

Notable columns:

- `id` (identity PK), `user_id`, `created_at`
- `source_type` (`TEXT`) — constrained to `decision_report`, `compare_result`, or `saved_run`
- `source_id` (`BIGINT`)
- `scenario_profile`, `horizon_months`, `currency`, `region`, `model` (optional metadata)
- `dossier_json`, `assumptions_json` (`JSONB`)

### 6.7 Plan and quota lifecycle

`get_or_create_user(...)`:

- creates user row on first seen request.
- resets selected counters on plan change.

Token policy:

- `check_token_limit` blocks when month total reaches plan cap.
- monthly reset uses UTC month string in `tokens_last_reset_month` (compared to current `YYYY-MM`).

API rate policy:

- free: 1/minute
- premium: 5/minute
- 60-second rolling window tracked via `api_window_start` + `api_calls_count`.

Email policy:

- free: 0/day
- premium: 10/day
- daily reset by UTC date string.

### 6.8 Token tracking semantics

`track_token_usage(...)`:

- ensures month boundary reset,
- then increments `total_tokens`.

`get_user_stats(...)`:

- lazily resets expired API window counter for display consistency.

### 6.9 Saved results storage accounting

`get_saved_results_usage_bytes(...)` estimates storage by summing lengths of key text/JSON columns.

This is used for save-time plan storage gating and usage UI meter.

### 6.10 Saved report and comparison caching behavior

Decision report caching:

- deterministic key = sorted run IDs joined by comma.
- same run set reuses previous report payload.

Comparison caching:

- same run pair (order-insensitive) reuses latest stored comparison.

Snapshot strategy:

- reports store `runs_json` so artifacts stay renderable even if original run rows change.

---

## 7) Agent Module Internals

## 7.1 `api/agent/model_fallback.py`

Core behavior of `generate_with_fallback(...)`:

1. Iterate model chain in order.
2. For each model:
   - invoke provider generate function with timeout wrapper,
   - parse tuple/string response shape,
   - return on success with fallback metadata.
3. On timeout:
   - do **not** fallback to next model,
   - re-raise timeout so caller can retry same model context.
4. On non-timeout errors:
   - detect transient via regex patterns,
   - fallback on transient,
   - fail fast on non-transient.
5. Raise runtime error if chain exhausted.

Transient detector includes 429/5xx, overloaded/capacity, and network/connection patterns.

## 7.2 `api/agent/idea_generation_agent.py`

Key functions:

- `_strip_code_fences`
- `_validate_idea_output_html`
- `generate_idea_agentic`

Generation contract:

- non-empty output,
- no markdown fences,
- minimum length threshold,
- HTML-only expectation.

Retry behavior:

- up to `max_attempts` (default 3),
- correction prompt includes previous validation errors,
- timeout gets explicit retry path,
- terminal fallback returns controlled error text.

Usage propagation:

- returns provider usage metadata when available.

## 7.3 `api/agent/rank_result_agent.py`

Purpose:

- rank model outputs within one run.

Important internals:

- strips HTML from outputs before prompt payload to reduce noise.
- enforces output schema:
  - `summary`
  - `ranked_models` covering all model IDs
  - unique rank values in 1..N
  - non-empty title/rationale per ranked entry
  - at least 5 `highlights`

Failure behavior:

- retry with validation error feedback (default 2 attempts),
- deterministic fallback ranking if validation continues to fail.

## 7.4 `api/agent/compare_results_agent.py`

Purpose:

- compare top outputs from two same-config runs.

Validation contract:

- winner in `{A, B, tie}`
- required summary
- non-empty `key_changes`
- required `winner_rationale`

Adds synthesized `decision_memo` structure even when missing from model payload.

Fallback behavior:

- safe tie-biased comparison payload when validation retries fail.

## 7.5 `api/agent/rank_report_agent.py`

Purpose:

- generate decision summary over multiple runs.

Validation contract:

- summary required,
- `ranked_runs` includes all run IDs,
- non-empty key insights,
- `risks` at least 5 bullets,
- `email_brief` object with subject/summary/highlights.

Fallback behavior:

- deterministic report fallback with conservative guidance.

## 7.6 `api/agent/recommend_combination_agent.py`

Purpose:

- choose best-fit persona + constraints for the selected industry from user-provided allowed lists.

Strict rules:

- recommended constraints must be exact-match items from allowed set,
- max 2 constraints,
- persona must be exact allowed persona ID,
- `reason_html` must include section wrapper and 3-5 list bullets.

Fallback behavior:

- deterministic first-option selection + fallback reason HTML.

## 7.7 `api/agent/email_agent.py`

Design:

- wraps email drafting in tool-calling LLM interaction.
- enforces one `send_email` call and one `log_action` call through prompt rules.

Execution flow:

1. run LLM with required tool choice,
2. extract tool-call arguments,
3. enforce subject hint override consistency,
4. send email via Resend API with PDF attachment,
5. return status and subject.

Failure behavior:

- retry LLM call (`max_retries + 1` attempts),
- fallback deterministic email payload on failure.

---

## 8) Prompt Architecture

### 8.1 Generation prompt contract (`instructions_prompt.py`)

`system_instructions(tone)`:

- binds persona voice,
- forbids unsupported factual invention,
- biases for concrete workflows and measurable outcomes.

`user_instruction(industry, constraint)`:

- defines exact HTML section order and required content blocks,
- enforces domain-specific constraints,
- includes hard requirements and edge-case guidance (e.g., no-code constraints).

### 8.2 Analysis prompt principles

Ranking, compare, and report agents all include:

- JSON-only output requirement,
- “use only provided data” rule,
- correction loop when schema validation fails.

### 8.3 Recommendation prompt principles

Recommend agent adds stricter constraints:

- exact string matching,
- no paraphrasing allowed values,
- bounded constraint count,
- HTML wrapper contract for explainability block.

---

## 9) PDF and Reporting Architecture (`api/utils/pdf_utils.py`)

### 9.1 Report types

`pdf_utils.py` renders three artifact classes:

1. Generated run report (`create_report_html`)
2. Decision summary report (`create_rank_report_html`)
3. Compare report (`create_compare_report_html`)

All are converted by `html_to_pdf_bytes(...)` using WeasyPrint.

### 9.2 Shared report rendering strategy

- Render complete HTML document string with embedded CSS.
- Escape non-trusted text values where necessary.
- Preserve model output HTML where feature requires full content rendering.
- Use consistent visual language (headers, section blocks, metadata fields).

### 9.3 Generated report structure

Includes:

- report header (brand, title, date),
- configuration table (industry, constraints, persona, models),
- per-model output sections,
- optional ranking section:
  - summary,
  - highlights,
  - ranked outputs with score and rationale.

### 9.4 Decision summary report structure

Includes:

- report metadata and generated timestamp,
- overall summary,
- ranked runs with rationale,
- key insights,
- risks,
- next steps,
- optional run snapshot data for context.

### 9.5 Compare report structure

Includes:

- Run A / Run B metadata,
- winner and summary,
- key changes,
- winner rationale,
- risks,
- top outputs compared.

---

## 10) Frontend Architecture (`pages/product.tsx`)

`pages/product.tsx` is a large stateful workspace component that centralizes feature orchestration.

### 10.1 High-level UI domains

Primary page regions:

1. Configuration panel (industry, constraints, persona, models, advanced settings)
2. Usage panel (tokens/API/email/storage)
3. Saved Results launcher card (four modal buttons)
4. Main results area with four tabs:
   - Generated Results
   - Compare Rank Results
   - Decision Summary Report
   - Execution Plan

### 10.2 Core state domains

Notable state groups:

- generation state: `results`, `isLoading`, `activeTab`, `rankResult`
- saved artifacts: `savedResults`, `savedComparisons`, `savedReports`
- execution artifacts: `savedStakeholderReports`, `stakeholderReport`, execution picker state
- compare state: `compareSelection`, `compareResult`, `compareError`, `compareLoading`
- report state: `reportSelection`, `reportOutput`, `reportEmail`, `reportLoading`, `decisionReport`
- modal state: `savedPanelMode`, `savedPanelPos`, drag refs, lock state
- UX feedback: notices, skeleton/loading flags, delete modals

### 10.3 Model selection and payload mapping

UI model IDs are concrete model IDs, but generation request sends provider labels:

- selected IDs -> labels (`OpenAI`, `Gemini`, `DeepSeek`, `Grok`)
- backend resolves labels to configured primary model IDs

This decouples frontend selection UX from backend fallback-chain internals.

### 10.4 Free vs premium UX gating

UI gating behavior:

- free users limited to one constraint and one model,
- premium-only controls include recommendation and advanced sliders,
- upgrade modal prompts when restricted controls are used,
- backend still enforces hard policy independently.

### 10.5 Usage polling and refresh

- `refreshUsage()` calls `/api/subscription`.
- periodic refresh interval runs while signed in.
- refresh button includes spinner and minimum display delay to reduce flicker perception.

### 10.6 Saved Results modal architecture

The Saved Results card opens one shared modal shell in one of four modes:

- `generated`
- `compare`
- `decision`
- `stakeholder` (Execution Plan)

Shared modal shell properties:

- fixed size (`h-[520px]`, max viewport cap),
- draggable by header,
- constrained to viewport bounds,
- overlay backdrop,
- outside click + Escape close behavior,
- lock mode during long-running compare/report actions,
- parent modal outside-click close is paused while delete-confirm dialogs are open.

### 10.7 Draggable modal implementation

Drag flow (`startSavedPanelDrag`):

1. Ignore drag if modal locked or click is on interactive control.
2. Capture pointer start and panel origin.
3. On mousemove, compute deltas and clamp left/top to viewport bounds.
4. Apply updated position via state.
5. On mouseup, detach listeners and stop drag.

Position management:

- `updateSavedPanelPos(forceCenter)` computes centered initial position,
- resize handler clamps position back into viewport when dimensions change.

### 10.8 Modal mode behavior

Generated mode:

- list saved runs,
- load or delete actions,
- header-level `Delete All` action beside `Refresh`,
- bulk-delete confirmation modal with record count,
- row-level pending-delete animation during bulk delete,
- load action closes modal and hydrates results area.

Compare mode:

- run selector (A/B),
- saved comparisons list,
- per-row `View` and `Delete` actions,
- list-header `Delete All` action on the right,
- bulk-delete confirmation + animated deleting state,
- fixed-height footer with status/error and Compare action.

Decision mode:

- run-selection controls,
- saved reports list with `View` and `Delete` actions,
- list-header `Delete All` action on the right,
- bulk-delete confirmation + animated deleting state,
- fixed footer with output mode/email input/generate action.

Execution Plan mode:

- saved execution plans list with `View` and `Delete` actions,
- list-header `Delete All` action on the right,
- same shared floating modal shell and drag/lock semantics,
- `View` hydrates Execution Plan tab with loading skeleton before content render.

### 10.9 Loading and hydration patterns

The UI uses staged loading patterns to avoid abrupt transitions:

- minimum-delay loaders (`ensureMinLoadingTime`),
- skeleton card (`ResultsSkeletonCard`) when loading saved artifact into main view,
- per-button spinners,
- animated status dots (`LoadingDots`) for compare/report in-progress status text,
- modal lock banner while long actions are in progress.

### 10.10 Generated tab blank-state guidance

Generated tab includes:

- header guidance message,
- detailed quick-start steps,
- premium upsell cue for Recommend Combination,
- optional advanced settings hints.

Compare and Decision tabs mirror this pattern with feature-specific quick-tip steps.

### 10.10b Decision Flow adaptive mode + hysteresis

The flow strip above the tab content uses an adaptive guidance mode:

- `guided` mode for stronger onboarding hints and next-step prompts
- `status` mode for compact artifact/status signaling

Switching is controlled by a global guidedness score with hysteresis:

- `GUIDEDNESS_SWITCH_TO_STATUS = 40`
- `GUIDEDNESS_SWITCH_TO_GUIDED = 60`

Applied behavior:

- when current mode is guided, switch to status only if `guidednessGlobal <= 40`
- when current mode is status, switch to guided only if `guidednessGlobal >= 60`
- within `41-59`, mode does not change

This prevents rapid mode toggling around a single threshold and keeps UX stable.

### 10.10c Persistent Step Guide panel (all tabs)

A structured Step Guide card is rendered directly below the flow strip in every workspace tab.

Shared structure:

- What you do here
- What you get
- When you should use it
- To move forward

Per-step CTA support:

- Compare tab -> `Generate Decision Summary`
- Decision tab -> `Generate Execution Plan`
- Execution tab -> `Export Plan`

Persistence and default policy:

- collapse state is tracked per step (`generated|insights|decision|stakeholder`)
- user manual toggle marks the step as touched
- touched steps keep user preference and are not auto-overridden
- untouched steps use adaptive default:
  - guided mode => expanded
  - status mode => collapsed

Storage model:

- key: `ideagen.flow.step_guide.v1:<user_or_anon>`
- payload includes:
  - `collapsedByStep`
  - `touchedByStep`
- legacy compatibility: older boolean-per-step payloads are still read and upgraded in-memory

Generated tab empty-state scenario policy now aligns with saved-artifact state:

- fresh/no artifacts -> Start by generating ideas
- saved artifacts exist/no selected run -> load from library or generate new run

### 10.11a Execution Plan terminology assist

Execution Plan cards and tables include inline tooltip icons on technical labels (for example: `ARPU`, `COGS`, `OpEx`, `Break-even`, `Year 1 Net`, `Confidence`, `Avg FTE`).

Design intent:

- reduce ambiguity for non-technical stakeholders,
- keep definitions in-context without navigating away,
- preserve compact report density while improving readability.

### 10.11b Execution Plan card-level info pills

Execution Plan panel titles now include a dedicated `Info` pill tooltip (`InfoPillTooltip` in `pages/product.tsx`) for plain-English, panel-level guidance.

Panels covered:

- Execution Plan
- Executive decision
- Business terms and definitions
- Execution blueprint
- Budget and unit economics
- Stakeholder ask
- Scenario outcomes (Year 1)
- Sensitivity analysis
- Monthly financial projection
- Resource plan
- Risk register
- Assumptions
- Profitability recovery plan

Design intent:

- explain what each panel is for before users parse metrics/tables,
- improve readability for non-technical stakeholders without adding visual clutter,
- keep contextual help colocated with the panel header instead of separate docs.

### 10.11 Delivery actions in main workspace

Download and email actions route to context-specific API endpoints:

- generated view -> `/api/download-pdf`, `/api/email`
- compare view -> `/api/compare-results/{id}/pdf`, `/api/compare-results/{id}/email`
- decision view -> `/api/rank-reports/{id}/pdf`, `/api/rank-reports/{id}/email`
- execution plan view -> `/api/stakeholder-reports/{id}/pdf`, `/api/stakeholder-reports/{id}/presentation`

### 10.12 Execution Plan architecture (Grounded Finance v2)

Execution Plan generation is split into deterministic finance + narrative composition.

Request path:

- `POST /api/stakeholder-report`
- accepts `source`, `scenario_profile`, `horizon_months`, `currency`, `region`, `output`, `finance_mode`

Modes:

- `grounded_v2` (default)
  - deterministic sections: `resources`, `costs`, `revenue_profit`, `scenarios`, `stakeholder_ask`, finance assumptions
  - finance baseline is now **run-conditioned** (still deterministic):
    - starts from industry assumption pack,
    - applies bounded multipliers derived from selected run constraints/persona/output signals/model confidence,
    - recalculates scenario probabilities and funnel assumptions per selected report/output.
  - LLM narrative sections: thesis phrasing, blueprint language, risk wording, plan narrative
  - output includes `proposal_disclaimer` and `sensitivity_analysis`
- `llm_v1` (compatibility path)

Validation:

- server-side dossier normalization and schema checks run after generation,
- decision gates and profitability recovery are computed and enforced in backend,
- provenance records `finance_mode`, `financials_grounded`, `formula_version`, and `narrative_model`.
- assumptions now include run-conditioned metadata (`selected_output_title`, model confidence, scenario mix, adjustment tags) for auditability.

---

## 11) End-to-End Runtime Sequences

## 11.1 Generate -> rank -> auto-save

```text
User clicks Generate Ideas
  -> frontend builds payload (industry, constraints, persona, model labels, advanced settings)
  -> POST /api
  -> backend runs multi-model generation concurrently
  -> backend optionally runs rank_result_agent
  -> backend returns results + rank_result + usage
  -> frontend updates UI and silently POSTs /api/saved-results
  -> saved list refreshes
```

## 11.2 Load saved generated result

```text
User opens Saved Results modal (Generated)
  -> frontend GET /api/saved-results
  -> user clicks Load
  -> frontend GET /api/saved-results/{id}
  -> modal closes
  -> workspace shows hydration skeleton
  -> generated tab state is replaced with saved payload
```

## 11.3 Compare flow

```text
User opens Saved Results modal (Compare)
  -> frontend loads saved runs + saved comparisons
  -> user chooses Run A and Run B
  -> click Compare
  -> POST /api/compare-results
  -> backend validates same configuration and runs compare agent
  -> backend saves comparison and returns payload
  -> modal closes, insights tab updates
```

## 11.4 Decision summary flow

```text
User opens Saved Results modal (Decision)
  -> frontend loads saved runs + saved reports
  -> user selects runs and output mode
  -> click Decision Summary Report
  -> POST /api/rank-report
  -> backend reuses cache or generates via rank_report_agent
  -> backend optionally emails and/or returns PDF
  -> frontend refreshes saved reports and loads latest into decision tab
```

## 11.5 Email and PDF flow

```text
User clicks Download PDF / Send Email
  -> frontend picks endpoint by active results tab
  -> backend renders PDF using html templates
  -> for email paths: backend runs email agent + sends via Resend
  -> UI reports success/failure status
```

## 11.6 Execution Plan flow

```text
User opens Decision Summary tab
  -> clicks Generate Execution Plan
  -> selector modal opens with ranked outputs (one selectable variant per run)
  -> user selects one output variant
  -> POST /api/stakeholder-report (finance_mode=grounded_v2)
  -> backend resolves source artifact and selected model output
  -> backend builds deterministic finance baseline
  -> backend composes narrative sections (LLM)
  -> backend validates/normalizes dossier and saves artifact
  -> selector modal closes
  -> workspace loads Execution Plan tab with hydration skeleton
  -> user can export PDF or Presentation report
```

---

## 12) Observability and Diagnostics

### 12.1 Backend logs

Logging exists at:

- endpoint orchestration level,
- agent lifecycle level (attempt, success, validation failure, fallback),
- model fallback level (try index, latency, transient detection),
- email agent audit log.

### 12.2 Diagnostic response headers

Some report endpoints add operational headers:

- `X-Report-Cached`
- `X-Report-Email-Sent`
- `X-Report-Email-Failed`
- `X-Report-Runs-Missing`

### 12.3 Frontend diagnostics UX

- usage notices/toasts for operation outcomes,
- spinner states on long actions,
- skeleton/hydration transitions for loaded artifacts,
- modal lock indicators during processing.

---

## 13) Security and Trust Boundaries

### 13.1 Auth and identity

- Clerk JWT bearer verification via JWKS and RS256.
- decoded claims (`sub`, `pla`) drive authorization and plan logic.

### 13.2 Data isolation

- all DB accesses are user-scoped (`user_id` filters),
- no cross-user artifact queries should be reachable through API contract.

### 13.3 Service trust boundaries

External providers used:

- Clerk (identity)
- OpenAI / Gemini / DeepSeek / Grok (generation/analysis)
- Resend (email delivery)

### 13.4 Current security notes

- `verify_aud=False` is intentionally used in JWT decode path.
- report payloads may include user-generated HTML content.
- no at-rest encryption layer beyond underlying storage platform.

---

## 14) Performance Characteristics and Scaling Constraints

### 14.1 Current operating profile

- synchronous request/response orchestration,
- concurrent fan-out for generation only,
- PostgreSQL-backed persistence,
- no async worker queue.

### 14.2 Latency contributors

Major contributors:

- external LLM API latency,
- ranking/compare/report post-processing calls,
- PDF rendering cost,
- email provider roundtrip.

### 14.3 Throughput constraints

Primary bottlenecks at scale:

- database connection pool sizing and long-running request occupancy,
- long-running report requests occupying API workers,
- no background execution channel for delivery-heavy workloads.

### 14.4 Existing mitigation choices

- cache reuse for compare/report artifacts,
- partial success response for generation,
- minimal-delay loading UX to stabilize perceived responsiveness.

---

## 15) Reliability and Failure Handling

### 15.1 Provider call failures

- transient provider errors can fallback to next model (generation flow),
- timeout behavior prefers retry over fallback in `model_fallback.py`,
- non-transient errors fail fast.

### 15.2 Validation failures

- schema/content validation triggers correction retries,
- exhausted retries yield deterministic fallback payloads.

### 15.3 Quota and gate failures

- API/token/email/storage limits return controlled error responses,
- frontend disables controls when limits are reached where possible.

### 15.4 Artifact backfill behavior

- compare email/pdf endpoints backfill missing `top_outputs` from source runs,
- rank-report pdf endpoint can reconstruct from run IDs when snapshot missing.

---

## 16) Known Implementation Gaps and Drift Points

These are important to track for maintainability:

1. **Mixed error response shape**
   - some endpoints return `detail` (HTTPException),
   - some quota paths return `{error: ...}` JSON payload.

2. **Decision report delete API mismatch**
   - frontend issues `DELETE /api/rank-reports/{id}`,
   - backend currently has no matching FastAPI delete route, despite DB helper existing.

3. **Static export routing assumptions**
   - route refresh behavior depends on static export path conventions and trailing slash discipline.

4. **Single-process coupling**
   - API, PDF rendering, and static serving are all in one process footprint.

5. **No background jobs**
   - report/email heavy operations are request-bound.

---

## 17) Hardening Roadmap (Architecture-Level)

Priority 1:

1. standardize API error schema (`code`, `message`, `details`)
2. add missing decision-report delete route if UI feature is expected
3. add request correlation ID propagation from frontend to backend logs
4. formalize provider timeout and retry policy per endpoint type

Priority 2:

5. move long-running report/email operations to async jobs
6. externalize persistence to managed SQL for concurrent load
7. separate static hosting from API runtime for independent scaling
8. add endpoint-level metrics (latency, fallback rate, error classes)

Priority 3:

9. define versioned API contracts and typed SDK for frontend
10. add idempotency semantics for report generation requests
11. formalize security posture around JWT audience verification contract

---

## 18) Function-Level Reference Index

This section is a compact index for where key behavior lives.

### 18.1 `api/index.py`

- App lifecycle: `startup_event`
- Auth: `CustomClerkHTTPBearer.__call__`
- Providers: `generate_openai_compatible`, `generate_gemini`
- JSON parse: `_extract_json_object`
- Plan gates: `get_user_plan`, `is_premium`, `require_premium`
- Endpoints:
  - `/api/subscription`
  - `/api/saved-results` (POST/GET/GET by id/DELETE)
  - `/api/compare-results` (POST/GET/DELETE)
  - `/api/compare-results/{id}/pdf`
  - `/api/compare-results/{id}/email`
  - `/api/rank-reports` (GET list, GET by id, GET pdf, POST email)
  - `/api/rank-report`
  - `/api` (generation)
  - `/api/download-pdf`
  - `/api/email`
  - `/api/recommend-combination`
  - `/health`

### 18.2 Persistence stack (see **§6**)

- `api/config.py`: `get_settings`, `reset_settings_cache`
- `api/database/session.py`: `get_engine`, `get_session_factory`, `get_session`, `session_scope`, `verify_database_connection`, `reset_engine`
- `api/database/models.py`: ORM table classes (`UserUsage`, `SavedResult`, `SavedRankReport`, `SavedComparison`, `SavedStakeholderReport`)
- `alembic/env.py` + `alembic/versions/*`: schema revisions
- `scripts/start_server.sh`: `alembic upgrade head` then Uvicorn

### 18.3 `api/db.py`

- Startup: `init_db` (connectivity check only; **not** DDL — Alembic applies schema)
- User lifecycle: `ensure_user`, `get_or_create_user`, `get_user`
- Limits: `check_token_limit`, `check_and_increment_api_call`, `check_and_increment_email`
- Usage: `track_token_usage`, `get_user_stats`
- Saved runs:
  - `save_results`
  - `list_saved_results`
  - `list_saved_results_full`
  - `get_saved_result`
  - `get_saved_results_by_ids`
  - `delete_saved_result`
  - `delete_all_saved_results`
  - `update_saved_result_rank`
  - `get_saved_results_usage_bytes`
- Rank reports:
  - `get_saved_rank_report`
  - `save_rank_report`
  - `get_saved_rank_report_by_id`
  - `list_saved_rank_reports`
  - `delete_saved_rank_report`
  - `delete_all_saved_rank_reports`
  - `update_rank_report_snapshot`
- Comparisons:
  - `get_saved_comparison`
  - `get_saved_comparison_by_id`
  - `save_comparison`
  - `list_saved_comparisons`
  - `delete_saved_comparison`
  - `delete_all_saved_comparisons`
- Stakeholder / execution plans:
  - `save_stakeholder_report`
  - `get_saved_stakeholder_report_by_id`
  - `list_saved_stakeholder_reports`
  - `delete_saved_stakeholder_report`
  - `delete_all_saved_stakeholder_reports`

### 18.4 Agent modules

- `model_fallback.py`: `generate_with_fallback`
- `idea_generation_agent.py`: `generate_idea_agentic`
- `rank_result_agent.py`: `rank_result_agent`
- `compare_results_agent.py`: `compare_results_agent`
- `rank_report_agent.py`: `rank_report_agent`
- `recommend_combination_agent.py`: `recommend_combination_agent`
- `email_agent.py`: `run_email_agent`, `send_report_email`

### 18.5 Frontend (`pages/product.tsx`) key orchestration functions

- Data fetchers:
  - `fetchSavedResults`
  - `fetchSavedComparisons`
  - `fetchSavedReports`
  - `refreshUsage`
- Generation and recommendation:
  - `generateIdeas`
  - `recommendCombination`
- Saved artifact operations:
  - `saveCurrentResults`
  - `loadSavedResult`
  - `deleteSavedResult`
  - `deleteComparison`
  - `deleteDecisionReport` (calls missing backend route)
- Compare/report orchestration:
  - `runCompare`
  - `runAgenticReport`
  - `downloadSavedReport`
- Delivery:
  - `downloadPDF`
  - `sendEmail`
- Modal behavior:
  - `openSavedPanel`
  - `startSavedPanelDrag`
  - `updateSavedPanelPos`

---

## 19) Related Docs

Use this file as primary architecture reference, then consult supporting docs for focused views:

- `technical_backend.md`
- `agentic_architecture.md`
- `api_reference.md`
- `data_model.md`
- `POSTGRES_MIGRATION_SPEC.md` (design notes for SQLite → Postgres + SQLAlchemy + Alembic)
- `deployment_runbook.md`
- `billing_limits.md`
- `security_privacy.md`
