# IdeaGen: Agentic Multi-Model Decision Platform

## Portfolio Capstone for AI Engineer Applications

## 1. Project Overview

IdeaGen is a production-style AI application that turns raw LLM generation into a structured decision workflow.
Users can generate ideas across multiple model providers, rank outputs, compare saved runs, and produce stakeholder-ready PDF or email reports.

This project demonstrates end-to-end AI engineering:

- multi-provider model orchestration,
- contract-first agent outputs,
- validation and retry loops,
- deterministic fallback behavior,
- cached decision artifacts,
- user-level quotas and plan gating,
- complete product UX and deployment packaging.

---

## 2. Problem Statement

Most AI idea tools stop at single-shot text generation. That fails in real decision environments because teams need:

- cross-model comparison,
- repeatable saved artifacts,
- explicit rationale for choosing one direction over another,
- exportable reports for non-technical stakeholders,
- predictable behavior under provider instability.

IdeaGen addresses that gap by implementing an opinionated decision pipeline, not just a prompt wrapper.

---

## 3. My Role and Scope

I owned architecture and implementation across backend, AI workflows, data model, and frontend product behavior.

Primary ownership:

- API orchestration and agent pipeline design (`api/index.py`)
- agent modules for generation, ranking, comparison, reporting, recommendation, and email (`api/agent/*.py`)
- persistence, quotas, and schema migration (`api/db.py`)
- reporting and PDF generation (`api/utils/pdf_utils.py`)
- workspace UX, saved-results modal workflows, and delivery actions (`pages/product.tsx`)
- Dockerized deployment path and runtime integration (`Dockerfile`, `next.config.ts`)
- architecture and technical documentation

---

## 4. Architecture Summary

```text
Browser (Next.js static UI)
  -> FastAPI API
      -> Auth verification (Clerk JWT + JWKS)
      -> Quota and plan checks (SQLite)
      -> Agent orchestration
      -> PDF rendering (WeasyPrint)
      -> Email dispatch (Resend)
  -> LLM providers (OpenAI, Gemini, DeepSeek, Grok)
```

Core runtime properties:

- Single Docker image serving both static frontend and API
- SQLite persistence under `/app/data/usage.db`
- Route-level orchestration (no external queue in current version)
- User-scoped saved artifacts and usage meters

---

## 5. Technology Stack

Frontend:

- Next.js (static export), React, TypeScript
- Clerk for auth session/token access

Backend:

- FastAPI, Python
- OpenAI SDK + Google GenAI SDK (provider integrations)
- SQLite for usage and artifact persistence
- WeasyPrint for HTML-to-PDF
- Resend for transactional email

Deployment:

- Multi-stage Docker build
- Uvicorn runtime
- Health endpoint and Docker healthcheck

---

## 6. Product Features Delivered

1. Multi-model idea generation for one configuration (industry, constraints, persona).
2. Per-run ranking with summary, highlights, and scored model ordering.
3. Saved results lifecycle: create, list, load, delete.
4. Compare Results mode (Run A vs Run B) with top-output diff insight.
5. Decision Summary Report across selected runs (or all runs).
6. PDF export and email delivery for generated, compare, and decision artifacts.
7. Premium-only recommendation for persona + constraints.
8. Usage tracking and plan-aware limits (API calls, tokens, emails, saved storage).

---

## 7. Core Agentic AI Development Patterns

### Pattern A: Orchestrator-Worker Architecture

FastAPI endpoints are the deterministic orchestrator; feature-specific agents are workers.

- Orchestrator responsibilities: auth, gating, sequencing, persistence, response shaping.
- Worker responsibilities: task-specific reasoning, structured output generation.

This keeps business behavior predictable while still using LLMs for specialized analysis.

### Pattern B: Contract-First Outputs

Agent outputs are treated as contracts, not free-form text.

- generation: HTML output contract
- ranking/comparison/report/recommendation: JSON contract with required fields

Invalid outputs are not accepted as successful results.

### Pattern C: Validation-Driven Retry

Each analysis agent retries with explicit correction feedback when validation fails.

Typical flow:

1. call model
2. parse output
3. validate schema/content
4. if invalid, append validation errors and retry

This materially improves robustness versus blind retries.

### Pattern D: Multi-Provider Fallback

The system uses ordered model fallback chains per provider family (`FALLBACK_CHAINS` + `generate_with_fallback`).

- transient non-timeout failures: fallback to next model
- timeout failures: retry context, not silent provider switch
- hard non-transient failures: fail fast

### Pattern E: Progressive Analysis Pipelines

Instead of one large prompt, the system composes stages:

- generate -> rank (single run)
- ensure rank -> select top outputs -> compare (two runs)
- load run set -> synthesize report -> deliver artifact

This produces decision-grade artifacts with traceable intermediate structure.

### Pattern F: Deterministic Safety Fallbacks

Each analysis module has fallback payload behavior:

- fallback ranking
- fallback comparison
- fallback decision report
- fallback recommendation selection
- fallback email payload

Practical effect:

- UI remains functional under partial model failure.
- Users receive structured outputs instead of dead-end errors.
- Delivery flows continue even if one AI step fails.

### Pattern G: Cache-Before-Infer

Expensive analysis is reused when possible.

- compare artifacts cached by run pair
- decision reports cached by normalized run ID key

Cache miss triggers inference; cache hit returns existing artifact and avoids extra token cost.

### Pattern H: Snapshot-Based Artifact Durability

Decision reports store run snapshots (`runs_json`) so historical reports remain renderable even if source runs later change or are deleted.

---

## 8. Workflow Deep Dive

### 8.1 Idea Generation (`POST /api`)

1. Verify auth and enforce API/token limits.
2. Build prompts from selected configuration.
3. Resolve requested model labels to concrete model IDs.
4. Execute model generation concurrently.
5. Validate output per model through generation agent.
6. Aggregate usage.
7. Run ranking agent for multi-model outputs.
8. Return results + ranking + usage.
9. Frontend auto-saves result set.

### 8.2 Compare Results (`POST /api/compare-results`)

1. Validate two distinct run IDs.
2. Enforce same-config requirement (industry/persona/constraints/model set).
3. Return cached comparison if available.
4. Backfill missing rank data if needed.
5. Select top output from each run.
6. Run compare agent and persist outcome.

### 8.3 Decision Summary (`POST /api/rank-report`)

1. Validate output mode (`pdf`, `email`, `both`) and input run set.
2. Enforce token and email limits.
3. Resolve cached report by normalized run-set key.
4. On cache miss, run report agent and store snapshot.
5. Render PDF and optionally send email.
6. Return stream or JSON status depending on requested mode.

### 8.4 Recommendation (`POST /api/recommend-combination`)

1. Premium gate enforced server-side.
2. Recommendation agent constrained to allowed options.
3. Strict exact-match checks for persona and constraints.
4. Return recommendation and explanation HTML.

---

## 9. Reliability Engineering and Guardrails

### 9.1 Reliability Controls

- output validation before persistence/use
- bounded retries with correction feedback
- deterministic fallbacks for each analysis path
- cache reuse for expensive analysis artifacts
- token usage accounting for cost visibility

### 9.2 Product Guardrails

- auth enforced with Clerk JWT verification
- premium-only routes protected on backend
- plan-aware quotas:
  - API calls/minute
  - monthly tokens
  - daily emails
  - saved storage bytes

### 9.3 UX Guardrails

- disabled actions when limits are reached
- loading and lock states for long-running operations
- modal behavior designed to prevent conflicting actions during processing

---

## 10. Data Model and Persistence Strategy

Main tables:

- `user_usage`
- `saved_results`
- `saved_comparisons`
- `saved_rank_reports`

Design choices:

- user-scoped queries for isolation
- JSON payload storage for flexible artifact evolution
- startup-time additive schema migration
- snapshot strategy for report reproducibility

This supports fast iteration while preserving operational continuity.

---

## 11. Security and Operational Considerations

Security controls implemented:

- JWT signature verification via JWKS
- user-scoped data access in persistence layer
- server-side plan/feature enforcement
- secrets loaded from environment variables

Operational controls:

- `/health` endpoint
- Docker healthcheck
- mounted persistent data volume for SQLite durability
- structured logs around generation, fallback, validation, and delivery paths

---

## 12. Frontend Engineering Notes

The product workspace (`pages/product.tsx`) manages:

- configuration inputs and advanced settings
- generated/compare/decision tabs
- saved-results modal with three modes
- draggable modal behavior with viewport constraints
- fixed action footers for compare and decision generation
- route-specific delivery actions (PDF/email by current tab)
- usage dashboard with refresh states

Goal: reduce friction between generation, evaluation, and report delivery in one session.

---

## 13. Tradeoffs and Engineering Decisions

1. SQLite over managed SQL  
Why: lower ops complexity and fast iteration.  
Tradeoff: lower write concurrency at larger scale.

2. Request-scope orchestration over background job queue  
Why: deterministic flow and simpler debugging.  
Tradeoff: long report/email operations stay request-bound.

3. Single container for UI + API  
Why: operational simplicity.  
Tradeoff: reduced independent scaling flexibility.

4. JSON artifact fields over fully normalized relational model  
Why: fast schema evolution for AI outputs.  
Tradeoff: more app-level validation and migration discipline required.

---

## 14. Challenges Solved During Implementation

1. Model output inconsistency  
Solution: strict validators + correction loops + deterministic fallbacks.

2. Cross-provider behavior differences  
Solution: provider-specific wrappers and ordered fallback policy.

3. Reproducible reporting from mutable saved data  
Solution: snapshot storage on rank reports.

4. Product UX under async latency  
Solution: loading skeletons, fixed footers, modal lock states, and explicit status messaging.

---

## 15. What This Project Demonstrates for AI Engineer Roles

This capstone demonstrates practical ability to:

1. Build full AI product systems, not only prototype prompts.
2. Design agentic workflows with deterministic orchestration.
3. Engineer reliability under provider and output instability.
4. Apply contract-first output governance for downstream safety.
5. Connect AI pipelines to production product UX and delivery channels.
6. Ship and operate a deployable stack with clear tradeoffs and roadmap.

---

## 16. Next Iteration Roadmap

1. Move report/email execution to async jobs with status polling.
2. Migrate persistence from SQLite to managed Postgres.
3. Standardize API error envelope across all endpoints.
4. Add request correlation IDs across frontend, backend, and provider calls.
5. Add metrics for validation-failure rate, fallback rate, and per-endpoint latency.
6. Add offline evaluation harness for ranking and compare quality regression checks.

---

## 17. Resume-Ready Bullets

- Built an agentic multi-model AI platform (FastAPI + Next.js) that generates, ranks, compares, and summarizes business concepts into decision-ready artifacts.
- Implemented contract-first output validation, correction loops, and deterministic fallback behavior across generation and analysis agents to improve runtime reliability.
- Engineered multi-provider inference orchestration (OpenAI, Gemini, DeepSeek, Grok) with ordered fallback chains, token tracking, and plan-aware quota enforcement.
- Delivered report pipeline integration (HTML -> PDF via WeasyPrint, email via Resend) with saved artifact lifecycle and snapshot-backed reproducibility.
- Designed and shipped full-stack user workflows for saved results, compare insights, and decision summary reporting with production-oriented guardrails.

---

## 18. Interview Walkthrough Script (5-7 Minutes)

1. Problem framing: why generation-only tools are insufficient for decision workflows.
2. Architecture overview: orchestrator-worker model and provider integration.
3. Reliability deep dive: validation, retries, fallbacks, and caching.
4. Feature deep dive: compare and decision-report pipelines.
5. Tradeoffs and roadmap: what is production-ready today and what scales next.

---

## 19. AWS Deployment (ECR + App Runner)

This project is designed to run in AWS with a containerized deployment flow:

```text
Local build
  -> Docker image
  -> Push to Amazon ECR
  -> App Runner service pulls image
  -> App Runner runs FastAPI container on port 8000
  -> Health check: /health
```

### 19.1 Deployment Steps

1. Authenticate Docker to ECR.
2. Build the container image using build args for Clerk public config.
3. Tag and push the image to ECR.
4. Create or update an App Runner service from that ECR image.
5. Configure runtime environment variables in App Runner.
6. Set health check path to `/health`.
7. Deploy and verify API plus static app routes.

### 19.2 Build and Push Commands

```bash
aws ecr get-login-password --region $DEFAULT_AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$DEFAULT_AWS_REGION.amazonaws.com

docker build --platform linux/amd64 \
  --build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY" \
  --build-arg NEXT_PUBLIC_CLERK_JWT_TEMPLATE="$NEXT_PUBLIC_CLERK_JWT_TEMPLATE" \
  -t ideagen-app .

docker tag ideagen-app:latest $AWS_ACCOUNT_ID.dkr.ecr.$DEFAULT_AWS_REGION.amazonaws.com/ideagen-app:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$DEFAULT_AWS_REGION.amazonaws.com/ideagen-app:latest
```

### 19.3 App Runner Runtime Configuration

Container settings:

- Port: `8000`
- Health endpoint: `/health`
- Auto deploy from ECR image: enabled (recommended)
- Custom domain: `ideagen.agentairg.site` (Route 53 mapping)

Environment variables to configure in App Runner:

- `CLERK_JWKS_URL`
- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `GEMINI_API_URL`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_API_URL`
- `GROK_API_KEY`
- `GROK_API_URL`
- `RESEND_API_KEY`
- `EMAIL_FROM` (optional override)
- `ALLOWED_HOSTS` (recommended: `ideagen.agentairg.site`)
- `TOKEN_LIMIT_FREE` (optional)
- `TOKEN_LIMIT_PREMIUM` (optional)
- `SAVED_RESULTS_LIMIT_FREE_BYTES` (optional)
- `SAVED_RESULTS_LIMIT_PREMIUM_BYTES` (optional)

### 19.4 Custom Domain Setup (Route 53 + App Runner)

Implemented target:

- `ideagen.agentairg.site`

Implementation sequence:

1. In App Runner service, open `Custom domains` and link domain.
2. Select hosted zone `agentairg.site` in Route 53.
3. Use subdomain `ideagen`.
4. Use `CNAME` for subdomain mapping.
5. Wait for App Runner custom domain status to become `Active`.

Validation commands:

```bash
dig ideagen.agentairg.site +short
curl -I https://ideagen.agentairg.site
```

### 19.5 Restricting Access to Canonical Domain

To prevent normal app access via the default App Runner URL (`*.awsapprunner.com`), host allowlist middleware is used.

Behavior:

- Allowed hosts are controlled by `ALLOWED_HOSTS`.
- Requests from non-allowed hosts return `403`.
- `/health` remains accessible to preserve App Runner health checks.

Production recommendation:

```bash
ALLOWED_HOSTS=ideagen.agentairg.site
```

### 19.6 Data Persistence Caveat (Important)

Current implementation uses SQLite (`/app/data/usage.db`) for:

- usage counters,
- saved results,
- saved comparisons,
- saved decision reports.

App Runner containers are ephemeral and can restart or scale horizontally. That means local SQLite storage is not durable/reliable for production multi-instance workloads.

Practical production implication:

- For serious production use on App Runner, migrate persistence to managed storage (for example Amazon RDS PostgreSQL) and keep object/report artifacts in durable backing stores where needed.

### 19.7 AWS-Ready Strengths in Current Design

- Single-container deploy simplicity (frontend + API together)
- Health endpoint and Docker healthcheck built in
- Environment-based secret/config management
- No hardcoded cloud dependencies in application logic

### 19.8 AWS Hardening Next Steps

1. Replace SQLite with RDS PostgreSQL.
2. Add centralized logging/metrics dashboards (CloudWatch).
3. Add structured request IDs for traceability across provider calls.
4. Add staged environments (dev/staging/prod) with separate ECR tags and App Runner services.
5. Add CI/CD pipeline for automated build, scan, push, and deploy.

---

## 20. Key File References

- `api/index.py`
- `api/db.py`
- `api/agent/idea_generation_agent.py`
- `api/agent/model_fallback.py`
- `api/agent/rank_result_agent.py`
- `api/agent/compare_results_agent.py`
- `api/agent/rank_report_agent.py`
- `api/agent/recommend_combination_agent.py`
- `api/agent/email_agent.py`
- `api/utils/pdf_utils.py`
- `pages/product.tsx`
- `Dockerfile`
- `next.config.ts`
- `ARCHITECTURE.md`
