# Operations: Objectives, KPIs, and QA

This repo deploys a tool-using chat agent (frontend + FastAPI API + Lambda worker + MCP tools).

## 1) Objectives

- Provide fast, reliable answers for engineering/system/deployment questions.
- Reliably execute tool-heavy tasks (web search, file reading, PDF generation, email delivery) via MCP tools.
- Maintain user-specific memory (approved items only) to improve future responses without storing sensitive data.

## 2) Success Metrics (KPIs)

These are the default metrics to track in CloudWatch Logs Insights, Upstash job records, and client UX.

- **Availability**
  - API `/health` success rate.
  - Job completion rate: `completed / (completed + failed)`.
- **Latency**
  - API `/chat` p50/p95 (sync mode) and enqueue latency (async mode).
  - Worker job duration p50/p95.
  - Tool duration per tool (optional, if enabled).
- **Quality**
  - Golden-set pass rate (see `backend/evals/`).
  - Memory validator compliance rate (approved-memory checks).
- **Cost**
  - Worker billed duration distribution.
  - Tool call counts per request.
  - Daily quota utilization:
    - token usage / token limit
    - pdf usage / pdf limit
    - email usage / email limit

## 3) Evaluation and QA

- A runnable evaluation harness and golden set live in `backend/evals/`.
- The golden set is meant for regression, not for benchmarking model capability.
- Add test cases whenever you ship a new tool, prompt contract, or routing rule.

## 4) Production Hardening Defaults

- Async mode avoids API Gateway REST integration timeout constraints.
- Worker memory is sized to reliably start MCP subprocesses.
- MCP startup has a timeout to prevent indefinite hangs.
- Model routing: tool-heavy intents route to Grok; Bedrock is used for plain Q&A by default.
- High-risk outputs run through canonical renderer + truth gate before return.
- Daily quotas are enforced server-side using provider-reported LLM token usage.

## 5) Observability

- Every request/job gets a `trace_id`.
- Worker and API logs include `trace_id` and `job_id` (when async).
- High-risk pipeline logs: `classify`, `execute`, `render`, `validate`, `fix_loop`.
- Quota logs:
  - `[quota] ...` summary per turn (backend, increments, before/after, remaining, exceeded)
  - `[quota_s3_cas] ...` conflict/success/error telemetry for S3 optimistic-concurrency writes

## 6) Sentry Monitoring (Backend)

Sentry is supported for API + worker monitoring.

- Enable by setting `SENTRY_DSN` in Lambda environment variables.
- Optional tuning vars:
  - `SENTRY_ENVIRONMENT` (defaults to `ENVIRONMENT` or `dev`)
  - `SENTRY_SERVICE` (recommended per function: `...-api`, `...-worker`)
  - `SENTRY_RELEASE` (for deploy correlation; image tag is a good value)
  - `SENTRY_TRACES_SAMPLE_RATE` (default `0.1`)
  - `SENTRY_PROFILES_SAMPLE_RATE` (default `0.0`)

Behavior:

- Unhandled FastAPI/Lambda errors are captured through Sentry integrations.
- Worker handled failures are captured explicitly before failure responses are persisted.
- Request/job tags include `trace_id`, `job_id`, `session_id`, and basic runtime context.
