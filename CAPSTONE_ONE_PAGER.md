# IdeaGen One-Pager (AI Engineer Capstone)

## Summary
IdeaGen is a production-style AI decision platform that turns raw LLM generation into structured, comparable artifacts. It supports multi-model idea generation, per-run ranking, run-to-run comparison, and decision summary reporting with PDF/email delivery. The system emphasizes contract-first outputs, validation + retry loops, deterministic fallbacks, and cached artifacts for reliability.

## Problem
Most idea generators stop at single-shot text. Teams need:

- cross-model comparison
- repeatable saved artifacts
- explainable decision rationale
- exportable reports
- stable behavior under provider failures

## Solution
IdeaGen implements a deterministic orchestration layer (FastAPI) with specialized agent modules for each analysis step. It enforces strict output contracts (HTML for generation, JSON for analysis), retries on validation failures, and uses ordered provider fallback chains. Outputs are saved and reusable; comparisons and reports are cached. PDFs and emails are generated through a reporting pipeline.

## Key Features
- Multi-model generation (OpenAI, Gemini, DeepSeek, Grok)
- Per-run ranking and highlights
- Run-to-run comparison with decision memo
- Decision summary report across selected runs
- PDF export + email delivery
- Premium-only recommendation of persona + constraints
- Usage quotas and storage limits

## Architecture Highlights
- Next.js static export served by FastAPI
- FastAPI orchestrates all AI workflows and persistence
- SQLite for usage and saved artifacts
- WeasyPrint for HTML to PDF
- Resend for transactional email
- App Runner + ECR deployment

## Core AI Engineering Patterns
- Orchestrator-worker design (API as control plane)
- Contract-first outputs + schema validation
- Correction retries with validation feedback
- Ordered model fallback chains
- Deterministic safety fallbacks per module
- Cache-before-infer for comparisons and reports
- Snapshot-based report durability

## Reliability and Guardrails
- Auth via Clerk JWT and JWKS verification
- Plan-aware quotas (API, tokens, email, storage)
- Backend-enforced premium gates
- Fallback payloads ensure usable output under failure

## Tech Stack
- Frontend: Next.js, React, TypeScript, Clerk
- Backend: FastAPI, OpenAI SDK, Google GenAI SDK
- Persistence: SQLite
- Reporting: WeasyPrint
- Email: Resend
- Deployment: Docker, AWS ECR, App Runner

## Deployment Notes
- Custom domain: `ideagen.agentairg.site`
- Host allowlist: `ALLOWED_HOSTS=ideagen.agentairg.site`
- App Runner health check: `/health`
- SQLite is not durable for multi-instance scale; migrate to RDS for production.

## File References
- `api/index.py`
- `api/agent/*.py`
- `api/db.py`
- `api/utils/pdf_utils.py`
- `pages/product.tsx`
- `Dockerfile`
- `ARCHITECTURE.md`
