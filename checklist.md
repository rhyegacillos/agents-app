# Launch-Ready Checklist

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


## Reliability
- Handle errors on every API path (generate, save, compare, decision, PDF, email).
- Add retries/backoff for transient provider issues.
- Provide clear user-facing errors without blocking the UI.
- Remove double-click or repeated action bugs.

## Data Integrity
- Prevent duplicate saves when reloading and re-saving.
- Ensure saved runs always load with their rankings and snapshots.
- Enforce consistent schemas for saved results, compare results, and decision summaries.
- Add migrations for renamed entities and legacy data cleanup.

## UX Clarity
- Keep metrics in a consistent single-line layout.
- Make action buttons consistently visible across views.
- Simplify selection flow for Compare and Decision Summary.
- Finalize tooltip wording and keep it consistent.

## PDF / Email Quality
- Correct filenames and timestamps for each report type.
- Ensure PDF content matches the active view (generated, compare, decision).
- Validate long-content layout (wrapping, spacing, headers).
- Ensure email subject lines and sender labels render correctly.

## Usage / Billing
- Enforce limits in backend and UI messaging.
- Show accurate usage with manual refresh.
- Implement plan gating for premium features.
- Provide upgrade prompts at the right moments.

## Security / Compliance
- Validate inputs and sanitize outputs.
- Keep secrets in env vars only.
- Add rate limits for public endpoints.
- Audit email sending and attachments.

## Analytics
- Track funnel events: generate, save, compare, decision, export, email.
- Monitor errors and timeouts by provider.
- Measure usage by plan tier.

## Support / Docs
- Add a short “how to use” guide in-app.
- Provide FAQ for common questions.
- Ensure empty states explain what to do next.

## Legal / Policy
- Terms of Service
- Privacy Policy
- Refund policy
- Finalize no-reply email disclaimer

## Testing
- Smoke tests for generate, save/load, compare, decision report, PDF export, email send.
- Basic regression checklist for UI views.
