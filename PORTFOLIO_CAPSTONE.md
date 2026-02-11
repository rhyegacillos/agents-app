# Autonomous Agentic Trader — Portfolio Case Study

Use this file as your capstone project write-up for LLM Engineer / Software Engineer applications.

---

## 1) Project Snapshot

**Project:** Autonomous Agentic Trader  
**Type:** Full-stack AI trading simulation platform  
**Stack:** FastAPI, Next.js, Docker, SQLite, OpenAI Agents SDK, MCP tools, Polygon API  
**Deployment Targets:** Local Docker, AWS ECR + EC2 via Terraform + GitHub Actions (OIDC)

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
- Added layered pricing resolution (`Polygon -> cache -> web -> unavailable`) and blocked trade execution when price is unavailable.

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
- Implemented infrastructure-as-code deployment path with Terraform:
  - existing EC2 adoption/import support,
  - optional SG rule management/import to avoid duplicate ingress errors,
  - optional Route53 DNS + HTTPS wiring.
- Implemented CI/CD deployment path with GitHub Actions:
  - OIDC role assumption (no static AWS keys),
  - build + push image to ECR,
  - smoke test,
  - terraform apply,
  - SSM-based EC2 container redeploy.
- Added idempotent IAM setup automation script for GitHub OIDC deploy role creation/update and policy attachment.

### What Terraform Is Used For (and Why)
- Terraform is used to define and control AWS infrastructure state for this app:
  - AWS region/provider selection
  - EC2 instance management (existing or new)
  - security group rule management
  - optional Route53 DNS record management
  - deployment outputs (public DNS/IP, image URI, rendered env content)
- Why Terraform:
  - keeps infra changes versioned and reviewable in code,
  - prevents manual console drift,
  - supports repeatable deploys across environments and contributors.

### What GitHub Actions Is Used For (and Why)
- GitHub Actions is used for the deployment execution pipeline:
  - authenticate to AWS via OIDC role (`AWS_ROLE_ARN_TRADER`),
  - build Docker image from repo state,
  - push image to ECR (`latest` + commit SHA tags),
  - run smoke checks before rollout,
  - apply Terraform and trigger EC2 redeploy through AWS SSM.
- Why GitHub Actions:
  - provides automated, branch-driven deployment,
  - removes dependency on local developer machine deploys,
  - centralizes deploy logs and rollback diagnosis in CI history.

---

## 4) Architecture Highlights

- **Control plane:** FastAPI (APIs, scheduler control, market status, static frontend serving)
- **Data plane:** trading engine child process (`trading_floor.py`)
- **Persistence:** SQLite (`accounts`, `logs`, `market`) + optional memory DBs
- **Frontend:** Next.js static export with typed API client
- **Isolation model:** research tools separated from execution tools via MCP boundaries

### High-Level Agentic Architecture and Communication

- A scheduler acts as the orchestrator and triggers each trader agent (Warren, George, Ray, Cathie) in sequence per cycle.
- Each trader receives a structured context package: persona strategy, account cash/holdings, recent transactions, market-state constraints, and execution rules.
- The trader reasons with its assigned LLM model, then chooses tools rather than writing directly to storage or APIs.
- Tool communication is routed through MCP servers over a standard request/response protocol, so the agent interacts with tools in a consistent way regardless of provider.
- Execution tools (buy/sell/get balance/get holdings/get price) mutate account state; research tools (fetch/brave/memory) provide external context but do not execute trades directly.
- Every tool call and response is logged into the runtime event stream; the API surfaces this as live logs and portfolio/ledger updates in the dashboard.
- This architecture separates decision-making (LLM agent) from action boundaries (tools), making the system easier to control, audit, and harden.

See detailed diagrams and internals in:
- `ARCHITECTURE.md`
- `ARCHITECTURE_DIAGRAMS.md`

---

## 5) Engineering Decisions (Why They Matter)

- **MCP boundaries:** separated research context gathering from execution tools for safer agent workflows.
- **Graceful degradation:** kept trading runtime alive even when external tools/APIs fail.
- **Read-only mode:** supports safer cloud operation where users monitor but cannot manually alter lifecycle.
- **Single-container packaging:** simplified deployment and reduced integration friction for demos/interviews.
- **Terraform + CI split of concerns:** Terraform owns infra state; GitHub Actions owns deploy orchestration and rollout sequence.
- **OIDC-first AWS auth:** avoids static access keys in CI and reduces credential management risk.

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
- Deployment automation with Docker/ECR/EC2 using Terraform + GitHub Actions
- IaC + CI/CD integration (infra state management + sequential release execution)
- UI/UX iteration for data-heavy operational interfaces

---

## 7) Suggested Resume Bullets

- Designed and implemented a full-stack autonomous trading platform using FastAPI, Next.js, Docker, and SQLite, integrating LLM agents with tool-based execution and live observability.
- Built a multi-agent runtime with MCP-backed tooling (accounts, market, web research, memory), enabling strategy-aware autonomous trade/rebalance cycles.
- Implemented resilience patterns for external dependency failures (rate limits, startup failures, degraded fallbacks), preserving runtime continuity and operator visibility.
- Delivered cloud-ready deployment workflow on AWS using Terraform + GitHub Actions (OIDC auth, ECR image pipeline, Terraform apply, SSM EC2 redeploy), plus read-only runtime controls.

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
