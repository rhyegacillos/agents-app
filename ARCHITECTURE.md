# IdeaGen Architecture (Implementation Reference)

This document describes the architecture that is **actually implemented** in this repository (`ideagen-saas-aws`), based on the current source code.

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
- deployment remains simple (single container process, SQLite persistence).

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
  |-- Plan & quota checks (api/db.py)
  |-- Agent orchestration (api/agent/*.py)
  |-- PDF rendering (api/utils/pdf_utils.py + WeasyPrint)
  |-- Email delivery (api/agent/email_agent.py -> Resend)
  |
  +--> SQLite (/app/data/usage.db)
  +--> OpenAI / Gemini / DeepSeek / Grok APIs
```

### 1.2 Runtime boundaries

- Frontend is built as static assets (`next export`) and served by FastAPI at root path.
- Backend API remains dynamic under `/api/*`.
- Authentication is enforced only on protected API routes (not on static assets).
- Data persistence is local SQLite (durable if `/app/data` volume is mounted).

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
- external DB with transactional concurrency guarantees,
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

- DB default path: `/app/data/usage.db`
- Container should mount `/app/data` for persistence between restarts.

### 2.6 Environment variable matrix

Backend/auth:

- `CLERK_JWKS_URL`

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
- `DB_PATH` (optional override)

Frontend env used in UI behavior:

- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
- `NEXT_PUBLIC_CLERK_JWT_TEMPLATE`
- `NEXT_PUBLIC_TOKEN_LIMIT_FREE`
- `NEXT_PUBLIC_TOKEN_LIMIT_PREMIUM`

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

- `api/db.py`
  - schema creation/migration.
  - usage counters and limit checks.
  - CRUD for saved runs/comparisons/reports.

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
- `startup_event()` runs `db.init_db()` to create tables and apply additive migrations.
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

## 6) Persistence Architecture (`api/db.py`)

### 6.1 Database connection model

- SQLite connection opened per function via `get_db()`.
- row factory returns dict-like `sqlite3.Row`.
- no ORM is used.
- all table relationships are managed in application logic.

### 6.2 Table schema details

#### `user_usage`

Purpose: user plan and quota counters.

Columns:

- `user_id` (TEXT PK)
- `plan` (TEXT)
- `total_tokens` (INTEGER)
- `api_calls_count` (INTEGER)
- `api_window_start` (REAL seconds timestamp)
- `emails_sent_count` (INTEGER)
- `emails_last_sent_date` (TEXT YYYY-MM-DD)
- `tokens_last_reset_date` (TEXT YYYY-MM)

#### `saved_results`

Purpose: persist generated runs.

Columns:

- `id` (INTEGER PK)
- `user_id`
- `created_at`
- `industry`
- `tone`
- `constraints_json`
- `models_json`
- `results_json`
- `rank_result_json`

#### `saved_rank_reports`

Purpose: persist decision summary reports and stable run snapshots.

Columns:

- `id`
- `user_id`
- `created_at`
- `run_ids_key` (sorted canonical key)
- `run_ids_json`
- `report_json`
- `runs_json` (snapshot payload)
- `model` (model used for analysis)

#### `saved_comparisons`

Purpose: persist diff/compare insights.

Columns:

- `id`
- `user_id`
- `created_at`
- `run_a_id`
- `run_b_id`
- `winner_run_id`
- `comparison_json`
- `model`

### 6.3 Startup migration strategy

`init_db()` applies additive migrations with safe `ALTER TABLE` calls wrapped in `try/except`:

- add `tokens_last_reset_date` to `user_usage`
- add `rank_result_json` to `saved_results`
- add `runs_json` to `saved_rank_reports`

This supports forward-compatible schema extension without external migration tooling.

### 6.4 Plan and quota lifecycle

`get_or_create_user(...)`:

- creates user row on first seen request.
- resets selected counters on plan change.

Token policy:

- `check_token_limit` blocks when month total reaches plan cap.
- monthly reset uses UTC month string in `tokens_last_reset_date`.

API rate policy:

- free: 1/minute
- premium: 5/minute
- 60-second rolling window tracked via `api_window_start` + `api_calls_count`.

Email policy:

- free: 0/day
- premium: 10/day
- daily reset by UTC date string.

### 6.5 Token tracking semantics

`track_token_usage(...)`:

- ensures month boundary reset,
- then increments `total_tokens`.

`get_user_stats(...)`:

- lazily resets expired API window counter for display consistency.

### 6.6 Saved results storage accounting

`get_saved_results_usage_bytes(...)` estimates storage by summing lengths of key text/JSON columns.

This is used for save-time plan storage gating and usage UI meter.

### 6.7 Saved report and comparison caching behavior

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
3. Saved Results launcher card (three modal buttons)
4. Main results area with three tabs:
   - Generated Results
   - Compare Rank Results
   - Decision Summary Report

### 10.2 Core state domains

Notable state groups:

- generation state: `results`, `isLoading`, `activeTab`, `rankResult`
- saved artifacts: `savedResults`, `savedComparisons`, `savedReports`
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

The Saved Results card opens one shared modal shell in one of three modes:

- `generated`
- `compare`
- `decision`

Shared modal shell properties:

- fixed size (`h-[520px]`, max viewport cap),
- draggable by header,
- constrained to viewport bounds,
- overlay backdrop,
- outside click + Escape close behavior,
- lock mode during long-running compare/report actions.

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
- load action closes modal and hydrates results area.

Compare mode:

- run selector (A/B),
- saved comparisons list,
- fixed-height footer with status/error and Compare action.

Decision mode:

- run-selection controls,
- saved reports list with View action,
- fixed footer with output mode/email input/generate action.

### 10.9 Loading and hydration patterns

The UI uses staged loading patterns to avoid abrupt transitions:

- minimum-delay loaders (`ensureMinLoadingTime`),
- skeleton card (`ResultsSkeletonCard`) when loading saved artifact into main view,
- per-button spinners,
- modal lock banner while long actions are in progress.

### 10.10 Generated tab blank-state guidance

Generated tab includes:

- header guidance message,
- detailed quick-start steps,
- premium upsell cue for Recommend Combination,
- optional advanced settings hints.

Compare and Decision tabs mirror this pattern with feature-specific quick-tip steps.

### 10.11 Delivery actions in main workspace

Download and email actions route to context-specific API endpoints:

- generated view -> `/api/download-pdf`, `/api/email`
- compare view -> `/api/compare-results/{id}/pdf`, `/api/compare-results/{id}/email`
- decision view -> `/api/rank-reports/{id}/pdf`, `/api/rank-reports/{id}/email`

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
- SQLite-backed persistence,
- no async worker queue.

### 14.2 Latency contributors

Major contributors:

- external LLM API latency,
- ranking/compare/report post-processing calls,
- PDF rendering cost,
- email provider roundtrip.

### 14.3 Throughput constraints

Primary bottlenecks at scale:

- SQLite write contention,
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

### 18.2 `api/db.py`

- Setup: `init_db`
- User lifecycle: `get_or_create_user`, `get_user`
- Limits: `check_token_limit`, `check_and_increment_api_call`, `check_and_increment_email`
- Usage: `track_token_usage`, `get_user_stats`
- Saved runs:
  - `save_results`
  - `list_saved_results`
  - `list_saved_results_full`
  - `get_saved_result`
  - `delete_saved_result`
  - `update_saved_result_rank`
  - `get_saved_results_usage_bytes`
- Rank reports:
  - `get_saved_rank_report`
  - `save_rank_report`
  - `get_saved_rank_report_by_id`
  - `list_saved_rank_reports`
  - `delete_saved_rank_report`
  - `update_rank_report_snapshot`
- Comparisons:
  - `get_saved_comparison`
  - `get_saved_comparison_by_id`
  - `save_comparison`
  - `list_saved_comparisons`
  - `delete_saved_comparison`

### 18.3 Agent modules

- `model_fallback.py`: `generate_with_fallback`
- `idea_generation_agent.py`: `generate_idea_agentic`
- `rank_result_agent.py`: `rank_result_agent`
- `compare_results_agent.py`: `compare_results_agent`
- `rank_report_agent.py`: `rank_report_agent`
- `recommend_combination_agent.py`: `recommend_combination_agent`
- `email_agent.py`: `run_email_agent`, `send_report_email`

### 18.4 Frontend (`pages/product.tsx`) key orchestration functions

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
- `deployment_runbook.md`
- `billing_limits.md`
- `security_privacy.md`
