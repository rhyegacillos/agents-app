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
- Log output format defaults to JSON (`LOG_JSON=true`) with keys:
  - `timestamp`, `level`, `logger`, `message`, `trace_id`, `job_id`
  - optional `event` and structured `fields`
- Standard event-key logs (for deterministic filtering in Sentry Logs):
  - `event=classify`
  - `event=execute.run_start`, `event=execute.run_done`, `event=execute.tool_summary`
  - `event=truth_gate.search_context`, `event=render.canonical`, `event=validate.pass`, `event=validate.blocked`
  - `event=fix_loop.attempt`
  - `event=quota.increments`, `event=quota.consume_failed`
  - `event=worker.start`, `event=worker.completed`, `event=worker.timeout`, `event=worker.canceled`

## 5.1 Refactor Changelog

### 2026-02-18: Backend modularization (no API contract change)

Scope:
- Extracted endpoint registration into router modules:
  - `backend/api/routers/core.py`
  - `backend/api/routers/chat.py`
  - `backend/api/routers/memory.py`
  - `backend/api/routers/files.py`
- Extracted API schemas into:
  - `backend/api/schemas.py`
- Extracted provider/runtime logic into:
  - `backend/services/chat_runtime/grok_runner.py`
  - `backend/services/chat_runtime/high_risk_flow.py`
  - `backend/services/chat_runtime/bedrock_runner.py`
- Centralized MCP subprocess logging/OTel bootstrap in:
  - `backend/mcp_tools/bootstrap.py`

Operational impact:
- Route paths and payload contracts are unchanged.
- Log event names used for dashboards/alerts are unchanged.
- Deployment shape (Lambda API + worker, API Gateway, MCP subprocess model) is unchanged.

Benefits:
- Faster incident isolation (routing vs orchestration vs provider runtime separated).
- Lower regression risk for provider-specific changes.
- Cleaner test seams for unit/integration QA.
- Reduced `server.py` complexity for on-call debugging.

## 6) OpenTelemetry (Vendor-Neutral Observability)

OpenTelemetry traces and logs are implemented for backend API + worker and exported via OTLP HTTP.

Enable with environment variables:

- `APP_TIMEZONE=Asia/Manila` (default app/log timezone)
- `OTEL_ENABLED=true`
- `OTEL_EXPORTER_OTLP_ENDPOINT=https://<collector-or-vendor>/v1/traces`
- `OTEL_EXPORTER_OTLP_HEADERS=key=value,key2=value2` (optional auth headers)
- `OTEL_SERVICE_NAME=<service-name>`
- `OTEL_ENVIRONMENT=<dev|prod>`
- `OTEL_TRACES_SAMPLE_RATE=0.1` (0.0-1.0)
- `OTEL_LOGS_ENABLED=true`
- `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=https://<collector-or-vendor>/v1/logs` (optional; auto-derived from traces endpoint)
- `OTEL_EXPORTER_OTLP_LOGS_HEADERS=key=value,key2=value2` (optional; falls back to traces headers)
- `OTEL_LOGS_MIN_LEVEL=INFO`

Implementation notes:

- FastAPI is auto-instrumented.
- Worker path uses manual spans around async job execution.
- Span attributes include `trace_id`, `job_id`, `session_id`, and risk/quota context.
- Python stdlib logs are exported through OTel log pipeline when enabled.
- OTel export is backend-agnostic; switch provider by changing OTLP endpoint/headers only.
