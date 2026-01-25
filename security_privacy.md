# Security + Privacy Overview

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
