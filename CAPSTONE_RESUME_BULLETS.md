# Autonomous Agentic Trader — Resume Bullets

Use these as plug‑and‑play options. Pick 3–5 per resume.

## LLM Engineer Focus

- Built a multi‑agent trading runtime (4 personas) using OpenAI Agents SDK with tool‑based execution boundaries via MCP.
- Designed the prompt + context pipeline (strategy, account state, market constraints) to drive deterministic tool calls and auditable decisions.
- Implemented resilience to external dependency failures (rate limits, tool startup errors) with degraded‑mode behavior and live observability.
- Integrated market data resolution with layered sources (`Polygon -> cache -> web -> unavailable`) and blocked trades on missing price signals.
- Delivered live agent telemetry (traces/logs) into a monitoring UI for real‑time auditability.

## Software Engineer Focus

- Built a full‑stack trading simulation platform (FastAPI, Next.js, SQLite) with operational dashboard and live execution logs.
- Implemented scheduler lifecycle APIs (start/stop/status/reset) and safe read‑only operation mode for cloud environments.
- Shipped single‑container deployment (API + static UI) with persistent data volumes.
- Automated AWS deployment using Terraform + GitHub Actions (OIDC auth, ECR build/push, Terraform apply, SSM redeploy).
- Added infrastructure guardrails: existing EC2 import, SG rule import to avoid duplicate ingress errors, optional Route53 + HTTPS wiring.

## Full‑Stack / Platform Hybrid

- Built a production‑style multi‑agent trading system that pairs LLM reasoning with tool‑gated execution and real‑time observability.
- Designed a dashboard for portfolio intelligence: holdings, transactions, timeline chart, and live logs with filters and tooltips.
- Implemented reliable deployment pipeline: OIDC‑based AWS auth, ECR image delivery, Terraform infra management, and EC2 redeploy automation.

## Quant/Trading Domain Angle

- Modeled portfolio state with cash/holdings separation, executed buy/sell flows, and maintained transaction ledger integrity.
- Added market‑aware trading controls and automated trading lifecycle policies (open/close, read‑only safety).

## ATS‑Friendly Short Bullets

- Multi‑agent LLM trading engine with MCP tool boundaries and audit‑friendly logs.
- Full‑stack dashboard + scheduler control built on FastAPI + Next.js.
- Terraform + GitHub Actions CI/CD to ECR + EC2 using OIDC (no static keys).
