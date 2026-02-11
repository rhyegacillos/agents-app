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

## 3) Evaluation and QA

- A runnable evaluation harness and golden set live in `backend/evals/`.
- The golden set is meant for regression, not for benchmarking model capability.
- Add test cases whenever you ship a new tool, prompt contract, or routing rule.

## 4) Production Hardening Defaults

- Async mode avoids API Gateway REST integration timeout constraints.
- Worker memory is sized to reliably start MCP subprocesses.
- MCP startup has a timeout to prevent indefinite hangs.
- Model routing: tool-heavy intents route to Grok; Bedrock is used for plain Q&A by default.

## 5) Observability

- Every request/job gets a `trace_id`.
- Worker and API logs include `trace_id` and `job_id` (when async).

