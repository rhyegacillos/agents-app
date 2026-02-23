# IdeaGen — Project One-Pager

## Problem
Most AI ideation tools stop at one-shot text generation. Teams still lack decision-grade outputs: cross-model evaluation, run-to-run comparison, saved evidence, and stakeholder-ready reports.

## Solution
IdeaGen is an agentic multi-model decision platform that turns raw LLM outputs into auditable decisions.

### Core Features
- Multi-model generation across OpenAI, Gemini, DeepSeek, and Grok
- Per-run ranking using a structured rubric (clarity, feasibility, differentiation, actionability, risk, stakeholder readiness)
- Run-to-run comparison with winner, rationale, and risk tradeoffs
- Decision Summary report across selected runs (1–5), with reusable snapshots
- Execution Plan (Investment Readiness Assessment) with deterministic financial modeling and auditable assumptions
- Export + sharing via PDF and email
- User-level controls: auth, quotas, premium gating, storage limits, and bulk artifact lifecycle

## Architecture
UI (Next.js) → FastAPI control plane → Agent workflows → LLM providers → Persistence → PDF/Email delivery.

Supporting services:
- SQLite persistence (`saved_results`, `saved_comparisons`, `saved_rank_reports`, `saved_stakeholder_reports`, `user_usage`)
- WeasyPrint-based PDF rendering
- Resend-based transactional email
- Clerk JWT authentication + JWKS verification

## Stack
- Frontend: Next.js, React, TypeScript
- Backend: FastAPI, Python, async orchestration
- AI/Providers: OpenAI SDK, Google GenAI, DeepSeek, Grok
- Data: SQLite (`/app/data/usage.db`)
- Reporting: WeasyPrint
- Auth + Email: Clerk + Resend
- Deployment: Docker, AWS ECR, AWS App Runner, Route 53 custom domain
- Observability/Guardrails: plan-aware usage quotas, contract-first structured outputs, schema validation + retries, provider fallback routing, cache-before-infer, snapshot durability, and deterministic fallbacks

## Why This Project Matters
The platform demonstrates production-style AI engineering: contract-first outputs, validation/retry loops, model fallback chains, cache-before-infer behavior, and deterministic financial modeling with auditable assumptions for higher-trust decisions.
