# Data Model / Schema

Current primary database:

- PostgreSQL

Schema ownership:

- SQLAlchemy models in [api/database/models.py](/home/repos/ideagen-saas-aws/api/database/models.py)
- Alembic revisions in [alembic/versions](/home/repos/ideagen-saas-aws/alembic/versions)

Production hosting target:

- Amazon RDS for PostgreSQL

Local development target:

- local PostgreSQL via Docker Compose

## 1. Schema Overview

The application stores five core persistent entities:

- `user_usage`
- `saved_results`
- `saved_rank_reports`
- `saved_comparisons`
- `saved_stakeholder_reports`

The migration from SQLite to PostgreSQL changed several storage details:

- JSON payloads are now `JSONB`
- timestamps are stored as timezone-aware datetimes
- primary keys on saved artifacts use Postgres identity columns
- dominant access patterns have explicit indexes
- schema evolution is versioned with Alembic instead of startup-time `ALTER TABLE` logic

## 2. Tables

### 2.1 `user_usage`

Stores usage counters and plan state per authenticated user.

Columns:

- `user_id` `text` primary key
- `plan` `text`
- `total_tokens` `bigint`
- `api_calls_count` `integer`
- `api_window_start` `timestamptz`
- `emails_sent_count` `integer`
- `emails_last_sent_date` `date`
- `tokens_last_reset_month` `text`
- `created_at` `timestamptz`
- `updated_at` `timestamptz`

Constraints:

- non-negative checks on token, API-call, and email counters

Relationships:

- one row per Clerk user subject

### 2.2 `saved_results`

Stores generated multi-model runs.

Columns:

- `id` `bigint` identity primary key
- `user_id` `text`
- `created_at` `timestamptz`
- `industry` `text`
- `tone` `text`
- `constraints_json` `jsonb`
- `models_json` `jsonb`
- `results_json` `jsonb`
- `rank_result_json` `jsonb`

Indexes:

- `(user_id, created_at)`
- `(user_id, id)`

Relationships:

- referenced logically by comparisons, rank reports, and stakeholder reports

### 2.3 `saved_rank_reports`

Stores decision summary reports derived from one or more saved runs.

Columns:

- `id` `bigint` identity primary key
- `user_id` `text`
- `created_at` `timestamptz`
- `run_ids_key` `text`
- `run_ids_json` `jsonb`
- `report_json` `jsonb`
- `runs_json` `jsonb`
- `model` `text`

Indexes:

- `(user_id, created_at)`
- `(user_id, run_ids_key, created_at)`

Notes:

- `runs_json` is a snapshot, not just a pointer list
- this is intentional so reports still render after source runs are changed or deleted

### 2.4 `saved_comparisons`

Stores compare-result artifacts.

Columns:

- `id` `bigint` identity primary key
- `user_id` `text`
- `created_at` `timestamptz`
- `run_a_id` `bigint`
- `run_b_id` `bigint`
- `winner_run_id` `bigint`
- `comparison_json` `jsonb`
- `model` `text`

Indexes:

- `(user_id, created_at)`
- `(user_id, run_a_id, run_b_id, created_at)`

Notes:

- comparison caching still uses app-level logic keyed on the compared run pair

### 2.5 `saved_stakeholder_reports`

Stores Execution Plan / stakeholder dossier artifacts.

Columns:

- `id` `bigint` identity primary key
- `user_id` `text`
- `created_at` `timestamptz`
- `source_type` `text`
- `source_id` `bigint`
- `scenario_profile` `text`
- `horizon_months` `integer`
- `currency` `text`
- `region` `text`
- `dossier_json` `jsonb`
- `assumptions_json` `jsonb`
- `model` `text`

Constraints:

- `source_type` limited to `decision_report`, `compare_result`, `saved_run`

Indexes:

- `(user_id, created_at)`
- `(user_id, source_type, source_id, created_at)`

Notes:

- `model` records the narrative-generation model used for the report
- the finance sections may still be deterministic even when `model` is present

## 3. Relationship Strategy

The schema still uses application-managed relationships for cross-artifact references.

That means:

- the app resolves `source_type/source_id`
- the app resolves `run_ids_json`
- some foreign-key-like guarantees remain enforced in application logic rather than relational constraints

This is deliberate because the artifacts are JSON-heavy and snapshot-oriented.

## 4. JSON Payload Conventions

The migration kept the same artifact concepts while changing storage from stringified JSON to native `JSONB`.

Examples:

- generated results payloads
- compare report payloads
- rank report payloads
- execution plan dossiers
- assumptions snapshots

Practical benefits:

- no repeated JSON serialization/deserialization around storage boundaries
- simpler querying and validation
- fewer string-decoding edge cases compared with the old SQLite text fields

## 5. Migration and Evolution

Schema changes now belong in Alembic revisions.

Current operational rule:

- do not modify production schema via ad hoc startup DDL
- create a revision
- apply with `alembic upgrade head`

The container startup wrapper runs Alembic automatically in the deployed container, but local direct backend runs still require the developer to run Alembic manually first.

## 6. Data Import Path

The repo includes a SQLite-to-Postgres import tool for historical data migration:

- [scripts/import_sqlite_to_postgres.py](/home/repos/ideagen-saas-aws/scripts/import_sqlite_to_postgres.py)

That tool exists for one-time migration/import scenarios. The application itself should now read and write only through PostgreSQL in normal operation.
