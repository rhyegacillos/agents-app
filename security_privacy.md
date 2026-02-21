# Security + Privacy Overview

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


## Data Handling
- Stored data includes: industry, persona, constraints, generated outputs, rankings, comparisons, and decision summaries.
- Email addresses are used only for sending reports when requested.
- Usage metrics (tokens, API calls, emails) are tracked per user.

## Data Retention
- Saved runs and reports are persisted in SQLite until deleted by the user.
- No automated purge is implemented.

## Third-Party Services
- **Clerk**: authentication and user identity.
- **LLM Providers**: OpenAI, Google Gemini, DeepSeek, Grok.
- **Resend**: email delivery.

## Email Policy
- Emails are transactional and sent only when the user requests delivery.
- Sender uses a no-reply address by default.
- Reports are attached as PDFs.

## Storage Security
- SQLite database stored in `/app/data/usage.db` inside the container volume.
- Access is controlled by server-side auth (Clerk token required for API requests).

## Recommendations
- Use HTTPS in production.
- Store secrets only in environment variables.
- Restrict container access and rotate API keys regularly.
