#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[startup %s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

if [[ -n "${DATABASE_URL_PROD:-}" || -n "${DATABASE_URL_LOCAL:-}" ]]; then
  log "Running Alembic migrations"
  alembic upgrade head
else
  log "Skipping Alembic migrations because no database URL is configured"
fi

log "Starting uvicorn"
exec uvicorn server:app --host 0.0.0.0 --port 8000 --log-level info --access-log
