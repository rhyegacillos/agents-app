# Launch-Ready Checklist

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
