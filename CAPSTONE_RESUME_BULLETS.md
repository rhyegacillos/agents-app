# IdeaGen Resume Bullets (AI Engineer)

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


## Portfolio-Ready Bullets (Concise)

- Built an agentic AI decision platform (FastAPI + Next.js) that orchestrates multi-model ideation, scoring, comparison, and report generation into stakeholder-ready outputs.
- Implemented a contract-first reliability layer with schema validation, correction retries, and fallback payloads across generation and analysis workflows.
- Designed and shipped **Grounded Finance v2** for Execution Plans: deterministic financial modeling + narrative-only LLM composition, including run-conditioned assumption adjustments to keep projections realistic and auditable.
- Added proposal-grade decision controls including go/conditional/no-go gates, profitability recovery logic, assumption provenance, and sensitivity stress testing.
- Positioned the final Execution Plan artifact as an **Investment Readiness Assessment** to unify strategic fit, financial gates, and delivery feasibility for stakeholder approval.
- Developed end-to-end reporting delivery (PDF + presentation export) with reusable saved artifacts, cache-aware retrieval, and modal-driven UX controls.
- Added in-context Execution Plan `Info` pill tooltips at card level so technical and non-technical stakeholders can interpret report panels without external documentation.
- Deployed on AWS App Runner from ECR with custom domain routing, host allowlist enforcement, and production-style health/runtime configuration.

## Explanation (Use for Interviews or Portfolio Notes)

- **What I built end-to-end:** I owned architecture and implementation across backend orchestration, AI workflows, persistence, and frontend product UX.
- **Why reliability matters:** I treated LLM outputs as contracts, not plain text, and added validation/correction loops so failure modes still return usable structured outputs.
- **How realism was improved:** I separated creative narrative generation from financial computation, so business projections are deterministic and auditable.
- **How decisions are made:** final recommendations are derived from explicit financial gates and stress-tested scenarios, not model tone alone.
- **Why this is production-style:** the system includes quotas, saved artifacts, exports, guarded destructive actions, and deployment-ready infra patterns.
