# Autonomous Agentic Trader — Portfolio Case Study

Use this file as your capstone project write-up for LLM Engineer / Software Engineer applications.

---

## 1) Project Snapshot

**Project:** Autonomous Agentic Trader  
**Type:** Full-stack AI trading simulation platform  
**Stack:** FastAPI, Next.js, Docker, SQLite, OpenAI Agents SDK, MCP tools, Polygon API  
**Deployment Targets:** Local Docker, ECR + EC2 (App Runner-compatible with constraints)

**One-line description:**  
Built a production-style autonomous multi-agent trading system where LLM traders research market context, execute strategy-driven trades through tool interfaces, and expose live operations/portfolio telemetry in a web dashboard.

---

## 2) Problem and Goal

Traditional demo bots are either:
- pure chat with no execution capability, or
- scripted execution with no transparent reasoning.

This project bridges both by combining:
- autonomous LLM reasoning,
- tool-based execution with explicit boundaries,
- and operator-grade observability in a full-stack app.

---

## 3) What I Built

### Agentic Trading Engine
- Implemented a scheduled multi-agent runtime with 4 trader personas (Warren, George, Ray, Cathie).
- Added alternating run modes (trade vs rebalance) per agent cycle.
- Used OpenAI Agents SDK with model abstraction across OpenAI / DeepSeek / Gemini / Grok.

### MCP Tooling Integration
- Connected agents to MCP servers for:
  - accounts + trading actions,
  - market price lookup,
  - optional web research (fetch + Brave),
  - optional memory persistence.
- Hardened MCP startup path so failed researcher tools degrade gracefully (no full-cycle crash).

### Market Data and Resilience
- Integrated Polygon market status and pricing paths.
- Added plan-aware behavior and fallback execution path when upstream API fails/rate-limits.
- Added cooldown-based handling for repeated provider failures to reduce log spam and retry storms.
- Added layered pricing fallback (`last-known price` before random fallback) to keep runtime stable while reducing unrealistic jumps.

### Full-Stack Control Desk
- Built a Next.js dashboard for:
  - market/trading status,
  - trader selection and performance timeline,
  - holdings and transaction ledger,
  - sortable/filterable transactions,
  - live logs with signal filtering.
- Implemented chart interactivity (zoom, pan, drag, marker tooltips).
- Implemented valuation-mode clarity:
  - strict flat mode support to freeze valuation between trades for execution-focused analysis,
  - semantic `Profit` / `Loss` labels in holdings and total summary cards for clearer stakeholder interpretation.

### Runtime Operations
- Added scheduler lifecycle API (start/stop/status/reset).
- Added runtime status tracking (`run_in_progress`, cycle timestamps).
- Added read-only deployment mode + optional market-auto start/stop policy.

### Containerization and Deployment
- Refactored into single-container architecture (FastAPI + static Next.js output).
- Prepared deployment guides for ECR -> EC2, including IAM/ECR flow and environment setup.

---

## 4) Architecture Highlights

- **Control plane:** FastAPI (APIs, scheduler control, market status, static frontend serving)
- **Data plane:** trading engine child process (`trading_floor.py`)
- **Persistence:** SQLite (`accounts`, `logs`, `market`) + optional memory DBs
- **Frontend:** Next.js static export with typed API client
- **Isolation model:** research tools separated from execution tools via MCP boundaries

See detailed diagrams and internals in:
- `ARCHITECTURE.md`
- `ARCHITECTURE_DIAGRAMS.md`

---

## 5) Engineering Decisions (Why They Matter)

- **MCP boundaries:** separated research context gathering from execution tools for safer agent workflows.
- **Graceful degradation:** kept trading runtime alive even when external tools/APIs fail.
- **Read-only mode:** supports safer cloud operation where users monitor but cannot manually alter lifecycle.
- **Single-container packaging:** simplified deployment and reduced integration friction for demos/interviews.

---

## 6) Role-Relevant Mapping

### LLM Engineer Relevance
- Agent orchestration and tool-calling workflows
- Prompt-context pipeline (strategy + account state + market constraints)
- Model-provider abstraction and multi-model compatibility
- Observability for agent traces/spans and execution events
- Reliability design under external API/tool failure

### Software Engineer Relevance
- Full-stack architecture and API-first design
- State management and persistence modeling
- Asynchronous scheduling and process lifecycle control
- Deployment automation with Docker/ECR/EC2
- UI/UX iteration for data-heavy operational interfaces

---

## 7) Suggested Resume Bullets

- Designed and implemented a full-stack autonomous trading platform using FastAPI, Next.js, Docker, and SQLite, integrating LLM agents with tool-based execution and live observability.
- Built a multi-agent runtime with MCP-backed tooling (accounts, market, web research, memory), enabling strategy-aware autonomous trade/rebalance cycles.
- Implemented resilience patterns for external dependency failures (rate limits, startup failures, degraded fallbacks), preserving runtime continuity and operator visibility.
- Delivered cloud-ready deployment workflows (ECR + EC2/App Runner paths), including read-only operation mode and market-driven auto lifecycle controls.

---

## 8) Interview Talking Points

- Why MCP is valuable for agentic systems: standard interfaces, composability, and safer tool boundaries.
- How trade execution remains controlled while allowing rich external research context.
- How you handled real-world instability (429s, auth limitations, process startup failures).
- How architecture choices change between demo scale and production scale (single instance vs distributed workers).

---

## 9) Known Constraints and Next Steps

- Current scheduler is single-instance oriented; distributed deployments need a worker/lock model.
- SQLite is practical for development but should move to managed Postgres for production.
- Optional `npx` MCP dependencies can be pinned/preinstalled for higher runtime reliability.
- Future upgrades: auth/RBAC, stronger audit controls, managed queue orchestration, metrics/alerting.

---

## 10) Personalization Fields (fill before submitting)

- **Your name:** `<YOUR_NAME>`
- **Your role in project:** `<SOLO | TEAM_MEMBER | LEAD>`
- **Project duration:** `<X weeks/months>`
- **Repository URL:** `<PRIVATE/GITHUB URL>`
- **Live demo URL (if any):** `<URL>`
