# Billing / Limits Specification

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


## Plans
Plan names are derived from Clerk tokens.
- Free: default plan (`u:free_user`)
- Premium: any plan in `PREMIUM_PLANS` (ex: `u:premium_subscription`, `u:premium`, `u:pro`)

## Limits (Defaults)
- **Monthly tokens**:
  - Free: 50,000 (`TOKEN_LIMIT_FREE`)
  - Premium: 500,000 (`TOKEN_LIMIT_PREMIUM`)
- **API calls per minute**:
  - Free: 1
  - Premium: 5
- **Emails per day (UTC)**:
  - Free: 0
  - Premium: 10
- **Saved results storage**:
  - Free: 100 MB (`SAVED_RESULTS_LIMIT_FREE_BYTES`)
  - Premium: 1 GB (`SAVED_RESULTS_LIMIT_PREMIUM_BYTES`)

## Enforcement Behavior
- API requests are blocked if rate limits or token limits are exceeded.
- Email sending is blocked if daily email limit is exceeded.
- Saving a result is blocked if storage limits are exceeded.

## Resets
- API rate limit resets every 60 seconds.
- Email limit resets daily (UTC).
- Token usage resets monthly based on `tokens_last_reset_date`.

## User Experience
- Frontend disables buttons when limits are reached.
- Usage card shows current usage with refresh tooltips.
