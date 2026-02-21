# IdeaGen One-Pager (AI Engineer Capstone)

## Documentation Sync: Adaptive Decision Flow + Step Guide (2026-02-20)

This document is synchronized with the latest UX/flow implementation in `pages/product.tsx`.

- **Adaptive flow modes**: UI now shifts between `guided` and `status` modes.
- **Hysteresis guard**: mode switching uses `guided -> status` at `<= 40` and `status -> guided` at `>= 60` to avoid flip-flop around a single threshold.
- **Persistent Step Guide**: every workspace step includes a structured guide panel (`What you do`, `What you get`, `When to use`, `To move forward`).
- **Per-step memory**: collapse/expand is saved per user and per step using local storage (`collapsedByStep`, `touchedByStep`).
- **Adaptive Step Guide defaults**: untouched guides auto-expand in guided mode and auto-collapse in status mode.
- **User override priority**: once a user manually toggles a step guide, that preference is preserved and not auto-overridden.
- **Generated empty-state scenarios**: first-time vs returning-with-library cases are explicitly separated for clearer onboarding.
- **Decision Summary behavior**: supports single-run and multi-run (1-5) synthesis; compare-first is recommended but not mandatory.
- **Compare behavior**: compares two selected saved runs and surfaces winner/diff insight; best quality when config alignment is preserved.
- **Execution handoff**: Decision Summary remains the source artifact for Execution Plan generation and export workflow.
- **Scope note**: this update is primarily frontend UX/state orchestration; backend endpoint contracts remain unchanged unless otherwise stated in backend/API docs.


## Executive Summary
IdeaGen is a production-style AI decision platform that converts raw LLM ideation into structured, auditable business decisions. The system supports multi-model generation, ranking, run-to-run comparison, decision summaries, and a final Execution Plan artifact (positioned as an **Investment Readiness Assessment**). It is designed to move from "interesting idea text" to "stakeholder-ready plan" with clear gates, saved evidence, and exportable deliverables.

## Problem
Most ideation tools stop at single-shot generation. That is insufficient for business decisions because teams need:

- comparative evaluation across models and runs
- persistent artifacts they can reload and defend
- explicit rationale for why one direction is stronger
- report outputs suitable for stakeholder review
- predictable behavior under model/provider instability

## Solution
IdeaGen uses a deterministic backend orchestrator (FastAPI) plus specialized agent workflows.

Pipeline:

1. Generate ideas across selected providers.
2. Rank model outputs for each run.
3. Compare top outputs between runs.
4. Build a Decision Summary from selected runs.
5. Build an Execution Plan from saved evidence.

The latest implementation adds **Grounded Finance v2**:

- deterministic finance computation for cost/profit sections
- deterministic run-conditioned assumption adjustments (constraints/persona/output-confidence)
- LLM narrative generation for strategic framing and plan wording
- proposal disclaimer + sensitivity analysis to communicate estimate boundaries

This hybrid design improves realism without losing narrative quality.

## Key Capabilities
- Multi-provider generation: OpenAI, Gemini, DeepSeek, Grok
- Per-run ranking with scored ordering and rationale
- Diff insight between run A and run B top-ranked outputs
- Decision Summary report over selected runs
- Execution Plan generation with `go / conditional_go / no-go`
- Execution Plan framed as an **Investment Readiness Assessment** for stakeholder approval decisions
- Execution Plan card-level `Info` pill tooltips (plain-English guidance per panel)
- PDF export (all report types) + presentation-style PDF for Execution Plan
- Saved artifact lifecycle (`View`, `Delete`, `Delete All`) with guarded modal UX
- Plan-aware usage controls (tokens, API calls, email, storage)

## AI Engineering Patterns Demonstrated
- **Orchestrator-worker architecture**: route-level orchestration + task-specific agents.
- **Contract-first outputs**: HTML/JSON schema boundaries per workflow.
- **Validation + correction loops**: invalid outputs are retried with structured repair prompts.
- **Fallback chains**: ordered provider/model fallback for resiliency.
- **Cache-before-infer**: comparisons and reports reused when keys match.
- **Snapshot durability**: decision artifacts remain valid even if source runs change.
- **Deterministic finance + narrative split**: grounded calculations with LLM explanation layer.

## Why Grounded Finance v2 Matters
Execution plans often look polished but can include invented numbers if fully model-generated. Grounded Finance v2 addresses that by enforcing deterministic financial sections and preserving AI only for narrative interpretation.

Practical effect:

- reproducible numbers for the same assumptions
- meaningful per-report variation (not flat industry-only projections)
- clearer decision gates
- less hallucination risk in budget/profit projections
- better stakeholder trust via provenance and assumption traceability

## Architecture Snapshot
- Frontend: Next.js + React + TypeScript
- Backend: FastAPI orchestration layer
- Persistence: SQLite (`saved_results`, `saved_comparisons`, `saved_rank_reports`, `saved_stakeholder_reports`)
- Reporting: WeasyPrint (HTML -> PDF)
- Email: Resend
- Auth: Clerk JWT + JWKS verification
- Deployment: Docker on AWS App Runner via ECR, custom domain + host allowlist

## Production-Like Controls and UX
- API/token/email/storage quota enforcement
- premium feature gating at UI + backend layers
- locked modal states during critical operations
- skeleton/spinner/dot loading feedback
- draggable, viewport-constrained saved-results shell
- in-context, panel-level info pills to improve readability for non-technical stakeholders

## Deployment Notes
- Custom domain: `ideagen.agentairg.site`
- Host allowlist enforced by `ALLOWED_HOSTS`
- Health endpoint: `/health`
- Current persistence uses SQLite (appropriate for demo/portfolio and single-instance deployment)

## Primary Code References
- `api/index.py` (route orchestration, grounded finance, validation)
- `api/agent/*.py` (generation/rank/compare/report/recommendation/email agents)
- `api/db.py` (persistence and usage/limit tracking)
- `api/utils/pdf_utils.py` (PDF and presentation renderers)
- `pages/product.tsx` (workspace UX and report workflows)
- `ARCHITECTURE.md` (full technical deep dive)
