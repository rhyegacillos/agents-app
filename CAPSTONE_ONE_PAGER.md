# Digital Assistant: Capstone One-Pager

## Project Summary
Digital Assistant is a production-oriented, **serverless** agentic AI web application that combines conversational LLM UX with real tools (web search, PDF generation, email delivery, file upload parsing, and user-approved memory). It runs on fully managed services (Lambda, API Gateway, S3, CloudFront, Upstash Redis) and is designed for reliability under real constraints: API timeouts, hallucination risk, quota governance, and deployment repeatability.

## Why This Is Serverless
- No application servers or VMs are provisioned or managed.
- Compute runs on-demand in AWS Lambda (API + worker), scales by concurrency, and is billed per invocation/runtime.
- HTTP entrypoint is API Gateway; static app delivery is S3 + CloudFront.
- Persistent objects/artifacts are stored in S3; transient state uses managed Upstash Redis.
- Deployments are immutable container images in ECR with infra fully managed by Terraform.

## Problem
Most chat demos fail when moved to production:
- Tool outputs are not verifiable.
- Long tasks time out in synchronous HTTP paths.
- Generated artifacts and links can be invalid or inconsistent.
- There is no usage governance for tokens and side-effect actions.

## Solution
This project implements a hybrid architecture:
- Low-risk conversational requests use a guarded prose path.
- High-risk/action requests use intent + tool execution + canonical validation.
- Long-running jobs are executed asynchronously by a worker Lambda.
- Quotas are enforced server-side (daily token, PDF, email limits) and surfaced in the UI.

## Architecture
- Frontend: Next.js chat UI with tool chips and daily quota indicators.
- API: FastAPI on AWS Lambda (container image), behind API Gateway.
- Worker: dedicated Lambda for asynchronous tool-heavy runs.
- Storage: S3 for uploads/downloads/memory artifacts; Upstash Redis for job state and quota state.
- Tools: MCP-based integrations for search, PDF, email, and memory extraction.
- IaC/CI-CD: Terraform + GitHub Actions for reproducible dev/prod deployment.

## Serverless Value
- Elastic scaling without capacity planning for API and worker paths.
- Lower ops overhead (no patching/monitoring of EC2 or Kubernetes nodes).
- Cost alignment to usage (idle periods do not pay for always-on compute).
- Fast environment parity via Terraform-based, repeatable infrastructure.

## Key Engineering Decisions
- Async job model (`/chat` -> `job_id` -> `/jobs/{id}` polling) to avoid API timeout failure modes.
- Truth gate and canonical rendering to reduce fabricated action claims and invalid links.
- Deterministic source/link validation for high-risk outputs.
- CAS-style quota update hardening for S3-backed fallback state.
- Provider-token-based quota accounting for LLM usage.

## Reliability and Operations
- Structured logs with trace and job correlation.
- Sentry-backed monitoring for backend errors and transaction traces.
- OpenTelemetry-aligned observability design (trace correlation across API, worker, and tool phases).
- Clear operator workflow documented in `OPERATIONS.md`.
- Regression coverage in backend tests plus lint-clean frontend.
- Risk-tier routing to preserve UX while protecting high-risk actions.

## What To Demo
1. Ask a research question with latest news -> sourced response.
2. Export response to PDF -> verified download link.
3. Send PDF by email -> tool-confirmed delivery message.
4. Upload a file and summarize.
5. Show daily quota counters updating for token/PDF/email actions.

## Tech Stack
- Python, FastAPI, openai-agents, MCP
- Next.js/React/TypeScript
- AWS Lambda, API Gateway, S3, CloudFront, ECR, IAM
- Upstash Redis
- Terraform, GitHub Actions
