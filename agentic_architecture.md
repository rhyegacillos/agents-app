# Agentic Architecture — IdeaGen

This document describes the *agentic* architecture of IdeaGen: how LLM calls are orchestrated, validated, retried, ranked, compared, and packaged into reports.

## 1) System Overview

```
Browser (Next.js)
  |
  |  HTTPS (Clerk JWT)
  v
FastAPI (api/index.py)
  |-- Auth guard (Clerk JWT + JWKS)
  |-- Usage + plan limits (SQLite)
  |-- Agent orchestration
  |-- PDF + Email delivery
  |
  +--> LLM Providers
  |     - OpenAI
  |     - Gemini
  |     - DeepSeek
  |     - Grok
  |
  +--> SQLite (data/usage.db)
  +--> PDF renderer (WeasyPrint)
  +--> Email (Resend)
```

## 2) Core Agentic Principles (Implemented)

1. **Strict output contracts**
   - Idea generation returns **HTML only** (no Markdown).
   - Comparison/ranking agents return **JSON only** with defined schemas.

2. **Validation + retries**
   - Each agent validates its output against explicit rules.
   - On validation failure, the agent re-prompts with correction instructions.

3. **Fallback chains per provider**
   - Each model ID maps to a provider + fallback list.
   - Transient errors fall back to the next model in the chain.

4. **Partial success**
   - Multi-model generation returns what succeeded and marks failures per model.

5. **Orchestration in FastAPI**
   - There is no agent-to-agent messaging. `api/index.py` orchestrates all agent calls.

## 3) Main Components

### Frontend (Next.js)
- Pages: `pages/index.tsx`, `pages/product.tsx`
- Calls the API endpoints and renders results.
- Auto-saves runs and requests comparisons/reports.

### API Orchestrator (FastAPI)
Entry: `api/index.py`
- Auth guard via Clerk JWT (JWKS verification, leeway, relaxed audience).
- Uses **async** execution for model calls.
- Tracks usage counters (API calls, tokens, emails).

### Agents (api/agent/*.py)
Each agent is a small, controlled LLM workflow:
- `idea_generation_agent.py` — HTML generation with validation.
- `rank_result_agent.py` — ranks outputs for a single run.
- `compare_results_agent.py` — compares top outputs across runs.
- `rank_report_agent.py` — decision-ready summary across runs.
- `recommend_combination_agent.py` — recommends persona/constraints.
- `email_agent.py` — writes and sends emails via Resend.

### Model Fallback
`api/agent/model_fallback.py`
- Wraps provider calls with timeout and fallback logic.
- Transient errors → fallback model.
- Timeouts → retry same model (no fallback on timeout).

### Storage (SQLite)
`api/db.py` and `data/usage.db`
- `user_usage`, `saved_results`, `saved_comparisons`, `saved_rank_reports`.
- Usage counters and quotas enforced per user.

### PDF + Email
- PDF HTML rendering: `api/utils/pdf_utils.py` (WeasyPrint).
- Email delivery: `api/agent/email_agent.py` (Resend).

## 4) Agentic Flows (Detailed)

### 4.1 Idea Generation (Multi‑Model)
Endpoint: `POST /api`

**Flow:**
1. Frontend sends `industry`, `constraints`, `tone`, and provider labels.
2. Backend resolves labels to concrete model IDs in `FALLBACK_CHAINS`.
3. For each model ID, `run_one(model_id)` is created.
4. **Parallelism:** all models run concurrently via `asyncio.gather(...)`.
5. Each `run_one` calls `generate_idea_agentic(...)`, which:
   - Executes `generate_with_fallback(...)`
   - Validates HTML output (no code fences, minimum length)
   - Retries with correction instructions on failure
6. Outputs are collected; failures are returned as error strings.
7. If multiple model outputs exist, `rank_result_agent(...)` ranks them.

**Key files:**
- `api/index.py` (orchestration)
- `api/agent/idea_generation_agent.py`
- `api/agent/model_fallback.py`

**ASCII flow (multi-model generation):**
```
UI -> POST /api (industry, constraints, tone, models)
 |
 v
resolve provider labels -> model IDs (FALLBACK_CHAINS)
 |
 v
for each model_id: run_one(model_id)  [PARALLEL via asyncio.gather]
 |
 v
generate_idea_agentic(...)  [per model]
 |  (retry loop)
 |  -> generate_with_fallback(...)   [sequential fallback]
 |  -> validate HTML
 |  -> if invalid: add correction + retry
 |
 v
collect results + usage
 |
 v
if >1 model -> rank_result_agent(...)
 |
 v
return results + rank_result + usage
```

**Deeper mechanics:**
- `run_one(model_id)` chooses provider + fallback chain.
- `generate_idea_agentic(...)` retries up to 3 times with correction instructions when validation fails.
- Validation checks:
  - No markdown/code fences
  - Minimum length
  - HTML output only
- Fallback behavior:
  - Transient errors (429/5xx/network) → fallback to next model in chain
  - Timeouts → retry same model (no fallback on timeout)

### 4.2 Run Ranking (Per‑Run)
Triggered inside idea generation when multiple models are present.

**Agent:**
`rank_result_agent.py`
- Returns structured JSON with scores, rationale, highlights.
- Validated and retried on schema errors.

**ASCII flow (per-run ranking):**
```
outputs from N models
 |
 v
rank_result_agent(...) [DeepSeek]
 |
 v
validate JSON schema
 |
 +-- invalid -> correction prompt -> retry (max 2)
 |
 v
rank_result (summary + ranked_models + highlights)
```

**Deeper mechanics:**
- Uses a rubric (clarity, feasibility, differentiation, actionability, risks, stakeholder readiness).
- Produces a rank list and a short summary; includes title mapping for display.

### 4.3 Compare Results (Across Runs)
Endpoint: `POST /api/compare-results`

**Flow:**
1. Validate runs have matching configuration.
2. Ensure each run has a rank result; generate if missing.
3. Pick each run’s top-ranked output.
4. `compare_results_agent(...)` produces:
   - winner, summary, key changes, risks, decision memo.
5. Save to `saved_comparisons`.

**Key files:**
- `api/agent/compare_results_agent.py`

**ASCII flow (comparison):**
```
UI -> POST /api/compare-results (run A id, run B id)
 |
 v
load both runs
 |
 v
ensure rank_result for each run (generate if missing)
 |
 v
select top-ranked output from each run
 |
 v
compare_results_agent(...)
 |
 v
validate JSON -> retry on errors
 |
 v
save comparison -> return result
```

**Deeper mechanics:**
- Enforces config match (industry/persona/constraints/models).
- Produces winner, summary, key changes, risks, and a decision memo.
- Falls back to a safe “tie” response if validation repeatedly fails.

### 4.4 Decision Summary Report (Rank Report)
Endpoint: `POST /api/rank-report`

**Flow:**
1. User selects 1–5 saved runs (or all).
2. If cached, return stored report.
3. Else `rank_report_agent(...)` produces decision summary:
   - overall summary, ranked runs, insights, risks, next steps.
4. Save report + run snapshot.
5. Optionally render PDF and send email.

**Key files:**
- `api/agent/rank_report_agent.py`
- `api/utils/pdf_utils.py`
- `api/agent/email_agent.py`

**ASCII flow (rank report):**
```
UI -> POST /api/rank-report (run IDs, output mode)
 |
 v
load runs -> check cache
 |
 v
rank_report_agent(...)
 |
 v
validate JSON -> retry on errors
 |
 v
save report + runs snapshot
 |
 +-- if output includes pdf/email:
 |      create_rank_report_html -> html_to_pdf_bytes
 |      send_report_email (optional)
 |
 v
return report (and/or pdf)
```

**Deeper mechanics:**
- Produces a decision-ready summary with risks + next steps.
- Stores a snapshot so report remains stable even if original runs are deleted.

### 4.5 Recommend Combination (Premium)
Endpoint: `POST /api/recommend-combination`

**Flow:**
1. Premium check.
2. Agent suggests constraints + persona.
3. Returns `reason_html` for display in UI.

**Key files:**
- `api/agent/recommend_combination_agent.py`

**ASCII flow (recommendation):**
```
UI -> POST /api/recommend-combination
 |
 v
require_premium
 |
 v
recommend_combination_agent(...)
 |
 v
validate JSON -> retry on errors
 |
 v
return recommended constraints + persona + reason_html
```

**Deeper mechanics:**
- Optimizes for workflow alignment and measurable outcomes.
- Emits `reason_html` for immediate UI display.

### 4.6 Email Delivery (Centralized Agent)
Used by multiple endpoints:
`/api/email`, `/api/compare-results/{id}/email`, `/api/rank-reports/{id}/email`, `/api/rank-report`

**Agent:**
`email_agent.py`
- Uses tool calls to produce HTML + audit log.
- Sends via Resend API.

**ASCII flow (email):**
```
UI -> request email endpoint
 |
 v
build email brief
 |
 v
email_agent (LLM w/ tools)
 |
 +-- must call send_email tool
 +-- must call log_action tool
 |
 v
Resend API -> email delivery
```

**Deeper mechanics:**
- System prompt enforces strict rules (salutation, disclaimer, max length).
- Tool calls produce HTML body and audit metadata.
- Fallback email is used if agent fails.

## 5) Deeper Agent Internals (All Agents)

### 5.1 idea_generation_agent.py
**Purpose:** Generate a single idea in strict HTML format.
**Algorithm:**
1. Build `system_instruction` + `user_content`.
2. Attempt up to 3 times:
   - Call `generate_with_fallback(...)`
   - Strip code fences
   - Validate output
3. On failure → correction prompt appended.
4. Returns HTML + usage metadata.

**Validation rules:**
- Output is non-empty
- No code fences
- Minimum length (>= 120 chars)

### 5.2 model_fallback.py
**Purpose:** Provider-resilient generation.
**Algorithm:**
1. Iterate models in fallback chain.
2. For each model:
   - Timeout guard (`asyncio.wait_for`)
   - On success → return text + usage
   - On transient error → try next model
   - On timeout → raise (caller handles)

### 5.3 rank_result_agent.py
**Purpose:** Rank model outputs for a single run.
**Algorithm:**
1. Ask model to return JSON ranking schema.
2. Validate required keys and formats.
3. Retry with correction prompt on error.
4. Return ranked list, summary, highlights.

### 5.4 compare_results_agent.py
**Purpose:** Compare two top outputs across runs.
**Algorithm:**
1. Build prompt with run A & B snapshots.
2. Request JSON with winner + rationale.
3. Validate → retry on schema errors.
4. Fallback to safe “tie” response.

### 5.5 rank_report_agent.py
**Purpose:** Produce decision-ready summary across runs.
**Algorithm:**
1. Build run set summary prompt.
2. Request JSON (summary, ranked runs, insights, risks).
3. Validate → retry on errors.
4. Save report + snapshot.

### 5.6 recommend_combination_agent.py
**Purpose:** Recommend optimal constraints/persona for industry.
**Algorithm:**
1. Provide available constraints/personas to model.
2. Request JSON + HTML reasoning.
3. Validate → retry on errors.

### 5.7 email_agent.py
**Purpose:** Draft and send transactional emails with tools.
**Algorithm:**
1. Provide brief + required subject line.
2. Require tool calls:
   - `send_email` (HTML body)
   - `log_action` (audit record)
3. Fail → fallback email body.

## 5) Concurrency Model

- **Across models:** parallel with `asyncio.gather(...)` in `/api`.
- **Within a model:** sequential retry/validation in `generate_idea_agentic(...)`.
- **Fallback:** sequentially tries model chain on transient errors.

## 6) Validation & Guardrails

### HTML Output (Idea Generation)
Validated by `idea_generation_agent.py`:
- No code fences
- Minimum length
- HTML sections required by prompt

### JSON Output (Agents)
Each JSON agent validates required keys and value types.
On error, it retries with a correction prompt.

## 7) Auth, Plans, and Limits

- Auth guard: `CustomClerkHTTPBearer` (JWKS + JWT decode).
- Premium plan check: `is_premium()` + `require_premium()`.
- Quotas enforced in `db.py` for:
  - API calls
  - Email sends
  - Token usage

## 8) Observability

Structured log prefixes:
- `idea_generation.*`
- `model_fallback.*`
- `rank_result.*`
- `compare_results.*`
- `rank_report.*`

These are emitted from agent modules and the API layer.

## 9) Key Files (Quick Index)

- **Orchestrator:** `api/index.py`
- **Agents:** `api/agent/*.py`
- **Fallbacks:** `api/agent/model_fallback.py`
- **Prompts:** `api/instructions/instructions_prompt.py`
- **PDF:** `api/utils/pdf_utils.py`
- **DB:** `api/db.py`
- **Frontend:** `pages/product.tsx`
