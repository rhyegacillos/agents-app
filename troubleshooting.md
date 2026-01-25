# Troubleshooting Guide

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
