# Troubleshooting Guide

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


## Common API Errors

### 401 / 403 Unauthorized
- Cause: Missing or expired Clerk token.
- Fix: Re-authenticate and retry.

### 402 Premium required
- Cause: Premium-only feature accessed by free plan.
- Fix: Upgrade plan or disable premium-only action.

### 413 Storage limit reached
- Cause: Saved results exceed plan storage limit.
- Fix: Delete older saved results or upgrade plan.

### 429 Too Many Requests
- Cause: API call rate limit, email limit, or monthly token limit reached.
- Fix: Wait for limit reset (per minute for API, daily for email, monthly for tokens).

### 404 Not found
- Cause: Saved run/report/comparison deleted or never existed.
- Fix: Refresh Saved Results and reselect.

### 502 Email delivery failed
- Cause: Resend delivery issue or invalid recipient.
- Fix: Retry with a valid address; check Resend logs.

---

## Compare Results Fails
Symptoms:
- Error: "Diff analysis requires the same industry, persona, constraints, and model set."

Fix:
- Ensure both runs were generated with the exact same configuration.

---

## Ranking Missing
Symptoms:
- Ranking skipped or shows "Ranking not available for a single model."

Fix:
- Generate with at least two models enabled.

---

## PDFs Not Rendering
Symptoms:
- Empty or malformed PDF.

Fix:
- Check system dependencies in the Docker image.
- Verify `xhtml2pdf` and font packages are installed.

---

## Usage Counters Not Updating
Symptoms:
- Current Usage does not change after actions.

Fix:
- Use the refresh icon in the Current Usage card.
- Verify `/api/subscription` returns updated counters.

---

## Logs
- Check container logs for errors:
  ```bash
  docker logs <container_id>
  ```
- For local run, check the terminal output.
