# Autonomous Agentic Trader — One‑Page Capstone

## Project Snapshot

- **Project:** Autonomous Agentic Trader  
- **Type:** Full‑stack AI trading simulation platform  
- **Stack:** FastAPI, Next.js, Docker, SQLite, OpenAI Agents SDK, MCP tools, Polygon API  
- **Deployment:** Local Docker and AWS ECR + EC2 using Terraform + GitHub Actions (OIDC)  

**One‑line description:**  
Production‑style multi‑agent trading system where LLM traders research context, execute strategy‑driven trades through tools, and expose live portfolio telemetry in a web dashboard.

## Problem

Most demo trading bots are either:
- pure chat with no execution,
- or scripted execution with no transparent reasoning.

Goal: combine autonomous LLM reasoning with tool‑based execution boundaries and operator‑grade observability.

## Solution (What I Built)

- **Multi‑agent runtime:** four trader personas (Warren, George, Ray, Cathie) with strategy‑driven cycles.  
- **Tool‑based execution:** agents call MCP tools for accounts, trades, prices, and research; no direct DB writes.  
- **Market resilience:** price resolution path (`Polygon -> cache -> web -> unavailable`) with trade blocking on missing prices.  
- **Control desk UI:** live logs, holdings, transactions, portfolio timeline, and controls for trading lifecycle.  
- **Deployment automation:** single‑container build and cloud deployment with Terraform + GitHub Actions.

## High‑Level Architecture (Agentic)

- Scheduler triggers each trader agent per cycle.
- Each agent receives structured context (strategy, account state, constraints).
- Agents decide actions via tools; tools enforce boundaries and persist results.
- MCP standardizes tool communication (execution vs research tools).
- Live logs and telemetry feed the UI for auditability.

## Deployment (How It Runs)

- **Terraform:** infrastructure state (existing or new EC2), optional SG rule management, optional Route53/HTTPS.  
- **GitHub Actions:** OIDC auth, build + push to ECR, smoke test, Terraform apply, SSM redeploy on EC2.  
- **Runtime:** single container (FastAPI + exported Next.js UI) with persistent data volume.

## Why It Matters (Engineering Highlights)

- Clear separation between reasoning (LLM) and action (tools).
- Resilient runtime under external API failure modes.
- Full‑stack observability and operator controls.
- Repeatable infrastructure and CI/CD with zero static AWS keys.

## Personalization (Fill Before Use)

- **Name:** `<YOUR_NAME>`  
- **Role:** `<LLM Engineer | Software Engineer>`  
- **Duration:** `<X weeks/months>`  
- **Repo:** `<URL>`  
- **Live Demo:** `<URL>`
