# Launch Roadmap

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


## Goal (as of 2026-01-25)
Deliver a stable, decision-ready product that users can trust and pay for, with reliable outputs, clear workflows, and exportable reports.

## Reason (as of 2026-01-25)
Monetization requires predictable reliability, professional outputs, and a clear user journey. This roadmap tracks what must be complete before charging customers.

## Checkpoint 1: Reliability Inventory + Failure Map (Completed — 2026-01-25)

### Core flows
- Generate ideas (`/api` in `api/index.py`)
  - Dependencies: LLM providers (OpenAI/Gemini/DeepSeek/Grok), `rank_result_agent` (DeepSeek), db usage tracking.
  - Failure points: provider timeouts/errors; unsupported params; model fallback chain failures; invalid JSON from `rank_result_agent`; partial model failures; token tracking errors.

- Save/load results (`/api/saved-results` GET/POST, `/api/saved-results/{id}`, DELETE in `api/index.py`)
  - Dependencies: SQLite (`api/db.py`), JSON serialization.
  - Failure points: db insert/read errors; JSON decode errors; size-limit rejection; duplicate save when UI re-saves same run.

- Compare results (diff insight) (`/api/compare-results` POST)
  - Dependencies: db read, `rank_result_agent` (DeepSeek) for missing ranks, `compare_results_agent` (DeepSeek), db save.
  - Failure points: missing run; config mismatch; `rank_result_agent` failure; `compare_results_agent` validation failure; db update/save failures.

- Compare report PDF/email (`/api/compare-results/{id}/pdf`, `/api/compare-results/{id}/email`)
  - Dependencies: db read; backfill top outputs; PDF generation (`html_to_pdf_bytes`); Resend email.
  - Failure points: missing comparison/run; backfill failure; PDF render errors; email send failures.

- Decision Summary Report (Rank Report) (`/api/rank-report`, `/api/rank-reports/{id}`, `/api/rank-reports/{id}/pdf`, `/api/rank-reports/{id}/email`)
  - Dependencies: db read/save; `rank_report_agent` (DeepSeek); PDF generation; Resend email; cached snapshots.
  - Failure points: missing runs; agent JSON validation failure; PDF generation; email send; stale/missing snapshot data.

- Idea report PDF/email (`/api/download-pdf`, `/api/email`)
  - Dependencies: PDF generation; Resend email.
  - Failure points: PDF generation; email send.

- Recommend combination (`/api/recommend-combination`)
  - Dependencies: Grok provider; `recommend_combination_agent`; db token tracking.
  - Failure points: provider errors; invalid agent output; fallback usage.

- Usage/subscription (`/api/subscription`)
  - Dependencies: db plan sync + usage aggregation.
  - Failure points: db read/lock; inconsistent usage windows.

### Cross-cutting reliability gaps
- External calls: no unified timeout/retry policy across providers/emails.
- Inconsistent error shapes: some endpoints return `HTTPException`, others return JSON `{error: ...}`.
- Snapshot consistency: compare/rank report flows rely on backfills when `top_outputs` are missing.

## Pending (as of 2026-01-25)
### Reliability (detailed steps)
- Step 2.1: Define a standard error shape for all endpoints (code, message, context). (Pending — 2026-01-25)  
  Why: Ensures consistent UI handling and easier debugging.
- Step 2.2: Update endpoints to use consistent `HTTPException` + JSON payloads. (Pending — 2026-01-25)
  Why: Avoids mixed error responses and silent failures.
- Step 3.1: Add timeouts to all external calls (LLMs, email). (Pending — 2026-01-25)  
  Why: Prevents requests from hanging and blocking user workflows.
- Step 3.2: Implement retry/backoff with capped attempts and clear fallback paths. (Pending — 2026-01-25)
  Why: Increases success rate under transient failures.
- Step 4.1: Make save idempotent by hashing payloads or checking last saved run. (Pending — 2026-01-25)  
  Why: Prevents duplicate entries when users reload or retry.
- Step 4.2: Enforce snapshot integrity for compare/rank reports at save time. (Pending — 2026-01-25)
  Why: Keeps reports consistent even if source runs change later.
- Step 5.1: Add start/success/fail logs for each flow (generate/save/compare/decision/pdf/email). (Pending — 2026-01-25)  
  Why: Enables monitoring and faster incident diagnosis.
- Step 5.2: Surface critical failures in the UI without blocking other actions. (Pending — 2026-01-25)
  Why: Users can recover without reloading the app.
- Step 6.1: Define smoke tests for each flow and a manual regression checklist. (Pending — 2026-01-25)  
  Why: Prevents regressions in core flows.
- Step 6.2: Add minimal automated tests for API error handling. (Pending — 2026-01-25)
  Why: Guarantees consistent error behavior across updates.

### UX Clarity (detailed steps)
- Step 1: Write a layout spec for key cards (Current Usage, Saved Results, Results tabs). (Pending — 2026-01-25)  
  Why: Prevents layout drift and inconsistent spacing.
- Step 2: Align button placement and visibility across Generated/Compare/Decision views. (Pending — 2026-01-25)  
  Why: Reduces user confusion and missed actions.
- Step 3: Simplify selection flows (Compare/Decision) with consistent show/hide and selection states. (Pending — 2026-01-25)  
  Why: Lowers cognitive load for non-technical users.
- Step 4: Finalize tooltip copy with clear definitions and step-by-step usage. (Pending — 2026-01-25)  
  Why: Makes the product self-serve without extra support.
- Step 5: Validate layouts at common widths (desktop/laptop/tablet). (Pending — 2026-01-25)  
  Why: Ensures a clean, readable UI on real devices.

### PDF / Email Quality (detailed steps)
- Step 1: Audit each PDF template for correct title, filename, and timestamp. (Pending — 2026-01-25)  
  Why: Users share PDFs directly with stakeholders.
- Step 2: Ensure PDF content matches the active view (Generated vs Compare vs Decision). (Pending — 2026-01-25)  
  Why: Avoids sending the wrong report content.
- Step 3: Fix wrapping/layout issues (tables, long titles, risk lists). (Pending — 2026-01-25)  
  Why: Keeps reports readable and professional.
- Step 4: Ensure email subject + sender labels render correctly in clients. (Pending — 2026-01-25)  
  Why: Improves trust and deliverability.
- Step 5: Verify attachments include correct report and timestamped filenames. (Pending — 2026-01-25)  
  Why: Prevents confusion when multiple reports are shared.

### Usage / Billing (detailed steps)
- Step 1: Confirm backend enforcement for tokens/API/email/storage. (Pending — 2026-01-25)  
  Why: Prevents overuse and protects costs.
- Step 2: Align frontend gating and messaging to backend limits. (Pending — 2026-01-25)  
  Why: Avoids user frustration and support tickets.
- Step 3: Add manual refresh and background refresh with clear refresh cadence. (Pending — 2026-01-25)  
  Why: Ensures usage stays accurate and trusted.
- Step 4: Implement upgrade prompts on limit hits and premium features. (Pending — 2026-01-25)  
  Why: Converts users at the right time.
- Step 5: Centralize plan config (limits, labels, copy). (Pending — 2026-01-25)  
  Why: Reduces drift between backend and UI.

### Security / Compliance (detailed steps)
- Step 1: Validate and sanitize all user inputs and stored HTML. (Pending — 2026-01-25)  
  Why: Prevents injection and corrupted data.
- Step 2: Ensure secrets are only read from env vars (no defaults in code). (Pending — 2026-01-25)  
  Why: Avoids accidental exposure in repos.
- Step 3: Add API rate limits and abuse protection. (Pending — 2026-01-25)  
  Why: Protects availability and cost.
- Step 4: Audit email sending and attachment handling. (Pending — 2026-01-25)  
  Why: Prevents data leaks and delivery issues.

### Analytics (detailed steps)
- Step 1: Define event schema for core actions (generate/save/compare/decision/export/email). (Pending — 2026-01-25)  
  Why: Enables consistent tracking across features.
- Step 2: Instrument frontend events and backend error/latency metrics. (Pending — 2026-01-25)  
  Why: Reveals drop-offs and reliability issues.
- Step 3: Create dashboards for conversions, errors, and usage by plan. (Pending — 2026-01-25)  
  Why: Guides product and pricing decisions.

### Support / Docs (detailed steps)
- Step 1: Add in-app “How to use” guide for each feature. (Pending — 2026-01-25)  
  Why: Reduces onboarding friction for non-technical users.
- Step 2: Draft FAQ for common errors and billing questions. (Pending — 2026-01-25)  
  Why: Deflects support requests.
- Step 3: Improve empty states with short, action-based guidance. (Pending — 2026-01-25)  
  Why: Helps users move forward without guesswork.
- Step 4: Add support contact or escalation path. (Pending — 2026-01-25)  
  Why: Establishes trust and support readiness.

### Legal / Policy (detailed steps)
- Step 1: Draft Terms of Service. (Pending — 2026-01-25)  
  Why: Required for paid plans and legal coverage.
- Step 2: Draft Privacy Policy. (Pending — 2026-01-25)  
  Why: Required for data handling transparency.
- Step 3: Define refund policy and publish it. (Pending — 2026-01-25)  
  Why: Prevents billing disputes.
- Step 4: Finalize no-reply email disclaimer language. (Pending — 2026-01-25)  
  Why: Avoids customer confusion and compliance issues.

### Testing (detailed steps)
- Step 1: Document manual smoke tests for each flow. (Pending — 2026-01-25)  
  Why: Ensures quick verification before deploys.
- Step 2: Add automated API tests for error handling and validation. (Pending — 2026-01-25)  
  Why: Catches regressions early.
- Step 3: Create a release checklist with required screenshots/PDF checks. (Pending — 2026-01-25)  
  Why: Prevents incomplete releases.

## Pushbacks (as of 2026-01-25)
- None yet.
