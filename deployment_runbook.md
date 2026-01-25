# Deployment + Ops Runbook

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
