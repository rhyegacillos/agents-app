# Autonomous Agentic Trader - Project One-Pager

Research/education simulation; not financial advice.

## Problem
Most trading demos are either chat-only (no real execution path) or hardcoded scripts (no transparent reasoning). This project bridges both by combining autonomous LLM decision-making with tool-gated execution and live operational visibility.

## Key Features
- Multi-agent trading runtime with 4 strategy personas (Warren, George, Ray, Cathie).
- MCP tool boundaries for account actions, market lookup, web research, and memory.
- Resilient price path: Polygon -> cache -> web -> unavailable, with safety blocks on invalid prices.
- Operator dashboard with structured logs, trace events, holdings, transactions, and portfolio timeline.
- Scheduler control APIs for start, stop, status, and reset.
- Read-only and market-auto modes for safer cloud demos.

## Architecture
- Single Docker container serving FastAPI control APIs and static Next.js UI on port 8000.
- FastAPI is the control plane; trading engine runs as a managed child process data plane.
- Trader agents call MCP servers rather than mutating storage directly.
- Persistent state stored in SQLite (`accounts`, `logs`, `market`) plus optional memory DB per trader.
- External integrations include LLM providers, Polygon market data, Brave search, and fetch/memory MCP tools.

## Stack
- Backend: FastAPI, Uvicorn, Python 3.12.
- Agent Runtime: OpenAI Agents SDK + MCP tool servers (stdio).
- Frontend: Next.js (static export) + TypeScript.
- Data: SQLite.
- Infra/Deploy: Docker, AWS EC2 + ECR, Terraform, GitHub Actions (OIDC), SSM redeploy.

## Outcome
The project demonstrates end-to-end agentic system design: reasoning + tool execution + observability + deployable infrastructure in a production-style full-stack app.
