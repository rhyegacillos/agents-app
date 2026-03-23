# Current Usage Implementation Details

This document explains how IdeaGen tracks user quotas and usage after the migration from SQLite to PostgreSQL.

## 1. What Changed in the Migration

Usage tracking still works the same at the product level, but the storage mechanism changed significantly.

Old model:

- usage counters persisted in SQLite
- container-local durability assumptions
- ad hoc schema mutation during startup

Current model:

- usage counters persist in PostgreSQL
- schema is created by Alembic
- SQLAlchemy manages reads/writes
- production durability comes from RDS, not the container filesystem

The authoritative usage table is still `user_usage`, now implemented by the `UserUsage` model in [api/database/models.py](/home/repos/ideagen-saas-aws/api/database/models.py).

## 2. `user_usage` Table Shape

The current Postgres-backed `user_usage` shape is:

| Column | Type | Description |
| :--- | :--- | :--- |
| `user_id` | `text` PK | Clerk subject ID |
| `plan` | `text` | current user plan |
| `total_tokens` | `bigint` | accumulated token usage for current billing month |
| `api_calls_count` | `integer` | calls in the active rate-limit window |
| `api_window_start` | `timestamptz` | start of the current API-call window |
| `emails_sent_count` | `integer` | emails sent during the current UTC day |
| `emails_last_sent_date` | `date` | last email-sent UTC day |
| `tokens_last_reset_month` | `text` | billing reset marker in `YYYY-MM` form |
| `created_at` | `timestamptz` | row creation timestamp |
| `updated_at` | `timestamptz` | last update timestamp |

Check constraints enforce non-negative counters.

## 3. Backend Logic (`api/db.py`)

Usage logic still lives in [api/db.py](/home/repos/ideagen-saas-aws/api/db.py). The user-visible semantics did not change; the persistence engine did.

### 3.1 API call rate limiting

Product rule:

- Free: 1 call / minute
- Premium: 5 calls / minute

Behavior:

1. load or create the user row
2. compare current time with `api_window_start`
3. if more than 60 seconds elapsed, reset the call counter and move the window
4. if the current count is below the plan limit, increment and allow
5. otherwise block with a rate-limit message

### 3.2 Email quota

Product rule:

- Free: 0 emails / day
- Premium: 10 emails / day

Behavior:

1. compare current UTC date with `emails_last_sent_date`
2. if the date changed, reset the email counter
3. if count is below the plan limit, increment and allow
4. otherwise block

### 3.3 Token tracking

Token behavior:

- total tokens are accumulated from model usage returned by generation/report agents
- the tracked value resets when the month marker changes
- limits are plan-aware

Current defaults:

- `TOKEN_LIMIT_FREE=50000`
- `TOKEN_LIMIT_PREMIUM=500000`

These are environment-configurable.

### 3.4 Plan synchronization

The app still treats Clerk as the source of current plan truth.

On each request:

1. plan is read from the authenticated token/session context
2. stored plan is compared with the DB value
3. if it changed, short-window counters are reset

This keeps usage behavior aligned with upgrades/downgrades without a separate billing-sync process.

## 4. API Endpoints That Depend on Usage State

### `GET /api/subscription`

Purpose:

- returns current plan
- returns usage counters
- ensures the user row exists

### `POST /api`

Purpose:

- idea generation

Usage behavior:

- checks `check_and_increment_api_call`
- after generation, aggregates returned token usage
- persists updated usage totals

### `POST /api/recommend-combination`

Usage behavior:

- checks API call quota
- tracks tokens if the recommendation agent returns usage metadata

### Email endpoints

Usage behavior:

- call `check_and_increment_email`

## 5. Frontend Integration

The frontend in [pages/product.tsx](/home/repos/ideagen-saas-aws/pages/product.tsx) still treats the backend as the authoritative source of usage state.

Current frontend pattern:

- fetch `/api/subscription` on load
- merge fresh usage from generation/recommendation responses
- poll `/api/subscription` periodically to reflect server-side resets

This is important because:

- rate-limit windows expire on the server, not in the browser
- monthly token resets also happen on the server
- the UI should never be the source of truth for quota enforcement

## 6. Operational Notes After the Migration

### Database precondition

If the `user_usage` table does not exist, usage-gated endpoints will fail even before model calls run.

That is why container startup now runs Alembic before `uvicorn`.

### Production storage

In production, usage data is expected to live in RDS PostgreSQL.

This avoids:

- loss of counters on container restart
- non-durable local filesystem assumptions
- multi-instance divergence

### Local development

Local development should use Postgres too, not SQLite, so quota behavior is exercised against the same engine used in production.
