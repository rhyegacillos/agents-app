# Streaming Roadmap — API Gateway REST + Lambda Response Streaming

This roadmap covers the **future** migration from HTTP API (non‑streaming) to
**REST API with response streaming**, so `/chat/stream` can work reliably in AWS.

Status Legend:
- [ ] Planned
- [~] In progress
- [x] Done

---

## Goals
- Enable **SSE streaming** from `/chat/stream` in production.
- Keep the frontend API contract unchanged.
- Maintain full CORS support for CloudFront origin calls.
- Preserve current Lambda functionality (MCP tools, memory, PDF/email).

## Non‑Goals (for this roadmap)
- WebSocket streaming (separate option).
- Real‑time token stream in UI (only SSE events).

---

## Phase 0 — Decision + Requirements (1–2 days)
- [ ] Confirm streaming requirement (latency vs UX tradeoff).
- [ ] Decide **REST API** vs **Lambda Function URL** (this roadmap assumes REST API).
- [ ] Confirm Python streaming approach (Lambda Web Adapter for ASGI).
- [ ] Define max response time (target timeout; default 30–60s for SSE chunks).

---

## Phase 1 — Infrastructure (REST API) (2–4 days)
**Terraform changes:**
- [ ] Replace `aws_apigatewayv2_*` (HTTP API) with REST API resources:
  - `aws_api_gateway_rest_api`
  - `aws_api_gateway_resource` for `/chat/stream`, `/chat`, `/health`, etc.
  - `aws_api_gateway_method` per route
  - `aws_api_gateway_integration` (AWS_PROXY)
  - `aws_api_gateway_deployment` + `aws_api_gateway_stage`
- [ ] Enable **response streaming**:
  - Set `responseTransferMode = "STREAM"` on `/chat/stream` integration.
- [ ] Configure **binary media types** for SSE:
  - `text/event-stream`, `application/json` (as needed).
- [ ] Configure **CORS** at REST API (methods, headers, origins).
- [ ] Update `aws_lambda_permission` to REST API execution ARN.
- [ ] Update Terraform outputs:
  - `api_gateway_url` now points to REST API stage URL.

**Acceptance:**
- REST API deployment succeeds.
- `/health` returns 200 from REST API.
- `/chat/stream` reaches Lambda.

---

## Phase 2 — Runtime Streaming (Lambda Web Adapter) (3–5 days)
**Goal:** make Python FastAPI stream via SSE **without Mangum**.

**Container updates (ECR image):**
- [ ] Add **AWS Lambda Web Adapter** to image:
  - Place adapter binary in `/opt/extensions/lambda-adapter`.
- [ ] Set env:
  - `AWS_LWA_INVOKE_MODE=RESPONSE_STREAM`
  - `AWS_LWA_PORT=8080`
- [ ] Start ASGI server in container:
  - `uvicorn server:app --host 0.0.0.0 --port 8080`
- [ ] Ensure `/chat/stream` uses `StreamingResponse` with
  `text/event-stream` and flushes events.
- [ ] Remove or bypass `Mangum` for streaming entrypoint
  (keep it for local dev if desired).

**Acceptance:**
- `curl` receives streamed events (not buffered).
- Lambda logs show incremental events, not a single response chunk.

---

## Phase 3 — Frontend + Client Handling (1–2 days)
- [ ] Keep `/chat/stream` client contract unchanged.
- [ ] Add **fallback** to `/chat` if stream fails.
- [ ] Ensure status events (`searching`, `generating`) still display.
- [ ] Verify CORS headers on streamed responses.

---

## Phase 4 — Testing + Verification (2–3 days)
- [ ] Local test (Docker):
  - `curl -N` verifies streaming.
- [ ] Dev deploy test:
  - CloudFront → REST API → Lambda stream.
- [ ] Error handling tests:
  - timeout, tool error, validation error.
- [ ] Validate memory + MCP tools still work during SSE.

---

## Phase 5 — Rollout + Monitoring (1–2 days)
- [ ] Deploy REST API in **dev** first.
- [ ] Add CloudWatch dashboards: latency, errors, 5xx, throttles.
- [ ] Roll into **prod** after 24–48h in dev.
- [ ] Document new streaming constraints/limits.

---

## Risks / Constraints
- REST API is **more expensive** than HTTP API.
- Streaming response limits and timeouts require tuning.
- Python streaming relies on Web Adapter (additional moving part).
- CloudFront caching should be **disabled** for `/chat/stream`.

---

## Success Criteria
- `/chat/stream` delivers incremental SSE events under 1s TTFB.
- No “Connection closed” or CORS errors in browser console.
- Works end‑to‑end with MCP tools and memory flow.

