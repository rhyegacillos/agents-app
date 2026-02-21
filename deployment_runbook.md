# Deployment + Ops Runbook

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


## Build and Run (Docker)
1. Build the image:
   ```bash
   docker build \
     --build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY" \
     -t ideagen-app .
   ```
2. Run the container:
   ```bash
   docker run -p 8000:8000 \
     -e CLERK_JWKS_URL=... \
     -e OPENAI_API_KEY=... \
     -e GEMINI_API_KEY=... \
     -e GEMINI_API_URL=... \
     -e DEEPSEEK_API_KEY=... \
     -e DEEPSEEK_API_URL=... \
     -e GROK_API_KEY=... \
     -e GROK_API_URL=... \
     -e RESEND_API_KEY=... \
     -e EMAIL_FROM="IdeaGen Reports <no-reply@agentairg.site>" \
     -v ideagen-data:/app/data \
     ideagen-app
   ```

## Health Check
- Container healthcheck hits `GET /health`.
- Manual check:
  ```bash
  curl http://localhost:8000/health
  ```

## Required Environment Variables
- `CLERK_JWKS_URL`
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` (build-time)
- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `GEMINI_API_URL`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_API_URL`
- `GROK_API_KEY`
- `GROK_API_URL`
- `RESEND_API_KEY`
- `EMAIL_FROM` (optional; default is no-reply)
- `ALLOWED_HOSTS` (recommended in production; example: `ideagen.agentairg.site`)

## Optional / Limits
- `TOKEN_LIMIT_FREE` (default: 50000)
- `TOKEN_LIMIT_PREMIUM` (default: 500000)
- `SAVED_RESULTS_LIMIT_FREE_BYTES` (default: 104857600)
- `SAVED_RESULTS_LIMIT_PREMIUM_BYTES` (default: 1073741824)

## Data Persistence
- SQLite file: `/app/data/usage.db`
- Stored in Docker volume: `/app/data`

## Backup / Restore
Backup:
```bash
docker cp <container_id>:/app/data/usage.db ./usage.db.backup
```
Restore:
```bash
docker cp ./usage.db.backup <container_id>:/app/data/usage.db
```

## Logs
- App logs stream to container stdout/stderr.
- Uvicorn access logs enabled by default.

## Common Ops Checks
- Validate env vars are set before starting.
- Ensure `/app/data` is mounted to persist usage/saved results.
- Check `/health` after deploy.

## App Runner Custom Domain (Route 53)
Use this when serving the app from a subdomain such as `ideagen.agentairg.site`.

1. In App Runner service -> `Custom domains` -> `Associate domain`.
2. Set:
   - Domain: `agentairg.site`
   - Subdomain: `ideagen`
   - Record type: `CNAME` (for subdomains)
3. If registrar is Route 53, choose `Amazon Route 53` and the hosted zone.
4. Confirm generated DNS records exist in Route 53.
5. Wait for domain status to become `Active`.

Verification:
```bash
dig ideagen.agentairg.site +short
curl -I https://ideagen.agentairg.site
```

## Host Allowlist Behavior (`ALLOWED_HOSTS`)
The backend enforces allowed request hosts to prevent access from unintended domains.

- Default allowed host includes `ideagen.agentairg.site` plus local dev hosts.
- Non-allowed hosts return `403` (`Host not allowed`).
- `/health` is exempt so App Runner health checks still succeed.

Recommended production setting:
```bash
ALLOWED_HOSTS=ideagen.agentairg.site
```

If you need multiple allowed domains:
```bash
ALLOWED_HOSTS=ideagen.agentairg.site,staging-ideagen.agentairg.site
```
