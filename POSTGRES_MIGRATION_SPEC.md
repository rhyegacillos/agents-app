# PostgreSQL + SQLAlchemy + Alembic Migration Spec

## 1. Purpose

This document defines the migration of the current persistence layer from local-file SQLite accessed through Python `sqlite3` helpers to a production-ready PostgreSQL stack using:

- PostgreSQL as the system of record
- SQLAlchemy 2.x as the database layer
- Alembic as the migration system

The goal is to make the backend scalable, operationally safer, and easier to evolve in production without changing the user-facing behavior of the app.

This spec is scoped to the current FastAPI backend and the persistence code centered in `api/db.py` and used throughout `api/index.py`.

## 2. Why This Migration Exists

The current persistence layer is sufficient for a single-instance MVP, but it is not a strong production foundation for AWS deployment at scale.

Current characteristics:

- The database is a local SQLite file.
- Each operation opens a direct SQLite connection.
- Schema evolution is performed at startup with inline `ALTER TABLE` statements.
- JSON payloads are stored as stringified JSON in text columns.
- Referential integrity is enforced in application logic only.
- The app container is responsible for both serving traffic and owning the DB file volume.

Production concerns with the current setup:

- SQLite is not suitable for multi-instance horizontal scaling.
- Local file storage complicates failover, backups, restore, and replication.
- Concurrent write pressure becomes a risk as usage grows.
- Startup-time schema mutation is unsafe as a long-term production migration strategy.
- The schema is under-modeled for validation, indexing, and controlled evolution.

## 3. Objectives

## 3.1 Primary Objectives

- Replace SQLite with PostgreSQL as the primary database.
- Replace raw `sqlite3` usage with SQLAlchemy-managed access.
- Replace startup schema mutation with Alembic migrations.
- Preserve all existing API behavior and business logic semantics.
- Support production deployment on AWS with a managed database.
- Enable safe future schema evolution.

## 3.2 Secondary Objectives

- Improve query performance for current access patterns with proper indexing.
- Upgrade JSON storage from text blobs to `JSONB` where appropriate.
- Introduce stronger constraints and data integrity checks.
- Isolate database access into a maintainable persistence layer.

## 3.3 Non-Goals

- No user-facing product redesign.
- No large business-rule rewrite.
- No immediate normalization of every JSON structure into relational tables.
- No forced adoption of SQLAlchemy ORM for complex domain logic if SQLAlchemy Core is simpler in a given area.
- No broad re-architecture of the frontend.

## 4. Current State Summary

The current schema and usage patterns are implemented in `api/db.py`.

Current tables:

- `user_usage`
- `saved_results`
- `saved_rank_reports`
- `saved_comparisons`
- `saved_stakeholder_reports`

Current table behavior:

- `user_usage` stores plan state, rate limits, token counts, and email counts per user.
- `saved_results` stores generated runs, including large JSON result payloads.
- `saved_rank_reports` stores decision summary reports and snapshots.
- `saved_comparisons` stores compare results between saved runs.
- `saved_stakeholder_reports` stores execution-plan style dossiers.

Current dominant query patterns:

- Filter by `user_id`
- Order by `created_at DESC`
- Lookup by row `id`
- Lookup `saved_rank_reports` by `user_id + run_ids_key`
- Fetch `saved_results` by `id IN (...)`
- Frequent counter updates in `user_usage`

Current structural gaps:

- No explicit secondary indexes are created.
- No foreign key constraints are declared.
- JSON is stored as text instead of native database JSON.
- Migrations are implicit and tied to app startup.

## 5. Target Architecture

## 5.1 Database

The production database will be PostgreSQL 16+ hosted as a managed AWS service.

Preferred target:

- Amazon RDS for PostgreSQL

Acceptable alternative:

- Amazon Aurora PostgreSQL-Compatible Edition

The database will become a separate managed dependency, not a file owned by the application container.

## 5.2 Python Data Layer

The backend will adopt:

- `SQLAlchemy>=2.x`
- `Alembic`
- `psycopg` v3 driver

Recommended implementation approach:

- Use SQLAlchemy 2.x style models and sessions.
- Use a synchronous SQLAlchemy engine for phase 1.
- Keep DB access isolated in a dedicated persistence layer rather than scattering ORM logic inside route handlers.

Rationale:

- This repo already uses synchronous DB access patterns inside helper functions.
- A synchronous SQLAlchemy migration is lower risk than combining a database migration with a full async data-access rewrite.
- The main scalability gain comes from PostgreSQL and proper pooling, not from async ORM usage.

Async SQLAlchemy can remain a future enhancement if profiling shows DB I/O becoming a dominant bottleneck.

## 5.3 Migration System

Alembic will become the only supported schema evolution mechanism.

Required rule:

- The application must stop mutating schema during startup.

Instead:

- migrations are generated and reviewed in source control
- schema changes are applied explicitly during deploy
- startup should only verify connectivity, not modify structure

## 5.4 Application Topology

Target production topology:

- stateless FastAPI application containers
- managed PostgreSQL instance
- environment-driven database URL
- shared deployment across multiple app instances without local DB coupling

This enables:

- horizontal app scaling
- rolling deploys
- backup/restore
- operational observability
- safer disaster recovery

## 6. Target Dependencies

## 6.1 Add

- `sqlalchemy`
- `alembic`
- `psycopg[binary]` or `psycopg`

## 6.2 Remove

- No package removal is required for `sqlite3` because it is part of Python stdlib.

## 6.3 Optional Additions

- `pydantic-settings` if configuration cleanup is desired
- `greenlet` if needed by the chosen SQLAlchemy usage pattern

## 7. Configuration Changes

## 7.1 New Environment Variables

- `DATABASE_URL`
- `DB_POOL_SIZE`
- `DB_MAX_OVERFLOW`
- `DB_POOL_TIMEOUT`
- `DB_POOL_RECYCLE`
- `DB_ECHO` for local debugging only

Example:

```env
DATABASE_URL=postgresql+psycopg://app_user:password@db-host:5432/ideagen
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800
DB_ECHO=false
```

## 7.2 Variables to Deprecate

- `DB_PATH`

This variable should remain temporarily supported only during transition if dual-read or fallback behavior is introduced. It must not remain part of the final production path.

## 7.3 Secrets Handling

- Credentials must be injected via AWS Secrets Manager, SSM Parameter Store, or equivalent secret management.
- The database password must not be committed to repo files or baked into the image.

## 8. Data Model Design

## 8.1 General Conventions

- Use `TIMESTAMP WITH TIME ZONE` (`timestamptz`) for timestamps.
- Use `JSONB` for JSON payloads currently stored as serialized text.
- Use explicit indexes for all dominant query paths.
- Use foreign keys where relationships are direct and stable.
- Keep polymorphic relationships application-enforced where the source can vary across multiple tables.

## 8.2 Table Mapping

### `user_usage`

Purpose:

- one row per authenticated user
- stores plan, monthly token state, API window counters, and email counters

Proposed columns:

- `user_id TEXT PRIMARY KEY`
- `plan TEXT NOT NULL`
- `total_tokens BIGINT NOT NULL DEFAULT 0`
- `api_calls_count INTEGER NOT NULL DEFAULT 0`
- `api_window_start TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `emails_sent_count INTEGER NOT NULL DEFAULT 0`
- `emails_last_sent_date DATE`
- `tokens_last_reset_month TEXT NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Notes:

- `tokens_last_reset_date` should be renamed to `tokens_last_reset_month` for semantic clarity.
- If a zero-downtime compatibility period is required, rename can be deferred and done in a later migration.

Indexes:

- primary key on `user_id`

Constraints:

- `total_tokens >= 0`
- `api_calls_count >= 0`
- `emails_sent_count >= 0`

### `saved_results`

Purpose:

- stores generated runs for each user

Proposed columns:

- `id BIGSERIAL PRIMARY KEY`
- `user_id TEXT NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `industry TEXT`
- `tone TEXT`
- `constraints_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `models_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `results_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `rank_result_json JSONB`

Indexes:

- `(user_id, created_at DESC)`
- `(user_id, id)`

Constraints:

- optional foreign key on `user_id` is not applicable unless a local users table is introduced

### `saved_rank_reports`

Purpose:

- stores decision summary reports and saved run snapshots

Proposed columns:

- `id BIGSERIAL PRIMARY KEY`
- `user_id TEXT NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `run_ids_key TEXT NOT NULL`
- `run_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `report_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `runs_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `model TEXT`

Indexes:

- `(user_id, created_at DESC)`
- `(user_id, run_ids_key, created_at DESC)`

Uniqueness:

- Do not add a unique constraint on `(user_id, run_ids_key)` in phase 1 because the current app allows multiple historical rows and returns the newest one.

### `saved_comparisons`

Purpose:

- stores compare outputs between two saved runs

Proposed columns:

- `id BIGSERIAL PRIMARY KEY`
- `user_id TEXT NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `run_a_id BIGINT NOT NULL`
- `run_b_id BIGINT NOT NULL`
- `winner_run_id BIGINT`
- `comparison_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `model TEXT`

Indexes:

- `(user_id, created_at DESC)`
- `(user_id, run_a_id, run_b_id, created_at DESC)`

Foreign keys:

- `run_a_id -> saved_results.id`
- `run_b_id -> saved_results.id`
- `winner_run_id -> saved_results.id` with nullable foreign key

Notes:

- The current app treats `(run_a_id, run_b_id)` as unordered in cache lookup.
- A future optimization may add canonical ordering fields such as `run_low_id` and `run_high_id` to support a cleaner uniqueness model.
- That normalization is out of scope for phase 1 unless implementation complexity remains low.

### `saved_stakeholder_reports`

Purpose:

- stores execution-plan dossiers derived from a decision report, compare result, or saved run

Proposed columns:

- `id BIGSERIAL PRIMARY KEY`
- `user_id TEXT NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `source_type TEXT NOT NULL`
- `source_id BIGINT NOT NULL`
- `scenario_profile TEXT`
- `horizon_months INTEGER`
- `currency TEXT`
- `region TEXT`
- `dossier_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `assumptions_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `model TEXT`

Indexes:

- `(user_id, created_at DESC)`
- `(user_id, source_type, source_id, created_at DESC)`

Constraints:

- `source_type` should be restricted to the currently supported values:
  - `decision_report`
  - `compare_result`
  - `saved_run`

Notes:

- Because `source_id` can refer to multiple tables depending on `source_type`, this relationship remains application-enforced in phase 1.

## 8.3 Timestamp Standard

All new persisted timestamps should use UTC-backed `timestamptz`.

Migration rule:

- Existing ISO timestamp strings from SQLite must be parsed and loaded into UTC `timestamptz`.

## 8.4 JSON Strategy

Current text columns containing serialized JSON will be migrated to `JSONB`.

Benefits:

- validated JSON storage
- simpler serialization/deserialization logic
- future indexability if specific fields become queryable
- fewer decode failures caused by malformed string handling

Phase 1 rule:

- Preserve the same logical payload shape currently returned to the application.

## 9. SQLAlchemy Design

## 9.1 Structure

Introduce a dedicated database package, recommended shape:

```text
api/
  db/
    __init__.py
    base.py
    session.py
    models.py
    repositories/
      usage.py
      saved_results.py
      comparisons.py
      rank_reports.py
      stakeholder_reports.py
```

Alternative naming is acceptable, but the responsibilities must remain separated:

- engine/session management
- metadata/model definitions
- persistence operations
- migration wiring

## 9.2 Session Pattern

Use a session-per-request or session-per-operation pattern with explicit transaction boundaries.

Requirements:

- no global mutable connection object
- connections returned to pool promptly
- commit and rollback behavior explicit
- route handlers must not leak sessions

## 9.3 Model Style

Use SQLAlchemy 2.x typed declarative mappings where it keeps the code clear.

Rule:

- avoid hiding critical query behavior behind overly abstract repository layers
- the code should remain easy to audit for exact SQL behavior

## 9.4 Serialization Boundary

Current helper functions in `api/db.py` parse JSON before returning Python dictionaries.

Target behavior:

- repository/service functions should continue returning Python-native structures to callers
- route handlers should not need to know whether storage is JSONB or text

## 10. Alembic Design

## 10.1 Migration Ownership

Alembic will own:

- table creation
- indexes
- constraints
- column additions and renames
- future data migrations where needed

The application will no longer call schema-changing SQL at startup.

## 10.2 Initial Migration Strategy

The initial Alembic baseline should create the PostgreSQL schema from scratch for new environments.

Recommended sequence:

1. create SQLAlchemy metadata/models
2. initialize Alembic
3. create initial baseline migration
4. add a dedicated data migration script for SQLite-to-Postgres import
5. remove startup schema mutation logic after cutover

## 10.3 Autogenerate Policy

Alembic autogeneration may be used, but every migration must be reviewed manually.

Required review points:

- indexes present
- constraints present
- JSONB types correct
- nullable vs non-nullable behavior intentional
- downgrade path is coherent when feasible

## 11. Data Migration Strategy

## 11.1 Migration Mode

Use an offline one-time data migration from SQLite to PostgreSQL.

Recommended source:

- the current SQLite database file from the running environment

Recommended target:

- newly provisioned PostgreSQL schema created by Alembic

## 11.2 Migration Tooling

Create a dedicated migration/import script rather than embedding data import in app startup.

Recommended behavior of the import script:

- connect to source SQLite database
- read rows table by table
- transform values into PostgreSQL-compatible shapes
- write in batches
- log row counts
- fail loudly on malformed records
- support dry-run validation mode

## 11.3 Transform Rules

### Timestamps

- Parse stored ISO strings to UTC-aware timestamps.

### JSON fields

- Parse stringified JSON.
- If parsing fails, log the row and abort unless an explicit recovery mode is enabled.

### Empty-string date fields

- Convert empty strings to `NULL` where the target type is `DATE`.

### Reset-month field

- Preserve value semantics when moving `tokens_last_reset_date` to the target column.

## 11.4 Migration Order

Recommended import order:

1. `user_usage`
2. `saved_results`
3. `saved_rank_reports`
4. `saved_comparisons`
5. `saved_stakeholder_reports`

Rationale:

- `saved_results` must exist before comparison foreign keys can be inserted.
- polymorphic stakeholder sources are application-managed and can be inserted after their likely dependencies.

## 11.5 ID Preservation

Existing integer IDs from SQLite should be preserved during import.

Reason:

- current application logic references saved rows by ID across tables
- preserving IDs minimizes migration risk and avoids rewriting embedded references

Requirement:

- after bulk import, PostgreSQL sequences must be advanced to at least the max imported ID

## 11.6 Validation Checks

The migration process must verify:

- per-table row counts match
- key referential relationships still resolve
- JSON columns successfully parse
- sample API read paths return expected results after cutover

## 12. Application Refactor Plan

## 12.1 Phase 1 Refactor Goal

Replace `api/db.py` implementation without changing its public behavior as consumed by `api/index.py`.

This means:

- function names may remain temporarily stable
- call sites in `api/index.py` should require minimal change in phase 1
- internal implementation can move from raw SQLite to SQLAlchemy-backed repositories

This reduces blast radius while the storage layer changes.

## 12.2 Startup Behavior

Current startup calls `db.init_db()`.

Target startup behavior:

- initialize engine/session factory
- optionally verify DB connectivity
- do not create or mutate schema

Migration commands must run before app startup in deployed environments.

## 12.3 User Counter Semantics

The following behaviors must remain unchanged during phase 1:

- one `user_usage` row per user
- plan changes reset API and email counters
- token counter resets monthly
- API rate counter resets on a 60-second window
- email counter resets daily

Implementation note:

- these counters should be updated transactionally in PostgreSQL
- race conditions must be reviewed because concurrent requests are more realistic in Postgres-backed multi-instance deployment

## 12.4 Concurrency Note

The current SQLite helper pattern is vulnerable to lost-update style behavior under concurrency.

When porting `check_and_increment_api_call`, `check_and_increment_email`, and `track_token_usage`, use one of:

- row locking with `SELECT ... FOR UPDATE`
- atomic update statements with checked predicates
- transaction-wrapped read-modify-write patterns

This is a required improvement, not an optional cleanup.

## 13. Indexing Plan

The following indexes are required in the initial PostgreSQL schema.

### `saved_results`

- `idx_saved_results_user_created_at` on `(user_id, created_at DESC)`

### `saved_rank_reports`

- `idx_saved_rank_reports_user_created_at` on `(user_id, created_at DESC)`
- `idx_saved_rank_reports_user_run_ids_key_created_at` on `(user_id, run_ids_key, created_at DESC)`

### `saved_comparisons`

- `idx_saved_comparisons_user_created_at` on `(user_id, created_at DESC)`
- `idx_saved_comparisons_user_runs_created_at` on `(user_id, run_a_id, run_b_id, created_at DESC)`

### `saved_stakeholder_reports`

- `idx_saved_stakeholder_reports_user_created_at` on `(user_id, created_at DESC)`
- `idx_saved_stakeholder_reports_user_source_created_at` on `(user_id, source_type, source_id, created_at DESC)`

Additional notes:

- primary keys already cover direct `id` lookups
- avoid premature JSONB GIN indexes in phase 1 because the current app does not query inside JSON payloads

## 14. Deployment and Cutover Plan

## 14.1 Phase Breakdown

### Phase A: Preparation

- add SQLAlchemy, Alembic, and Postgres driver dependencies
- create engine/session setup
- define models
- define Alembic baseline
- provision PostgreSQL environment

### Phase B: Compatibility Refactor

- refactor persistence code behind existing helper APIs
- preserve route behavior
- add tests for current DB semantics

### Phase C: Data Migration

- export/import SQLite data into Postgres
- verify row counts and sample reads

### Phase D: Staging Validation

- deploy app against PostgreSQL in staging
- run migrations via Alembic
- validate critical flows end to end

### Phase E: Production Cutover

- freeze writes or use a controlled maintenance window
- take final SQLite backup
- run final import if needed
- point production app to PostgreSQL
- run smoke tests

### Phase F: Cleanup

- remove SQLite-only code paths
- remove `DB_PATH`
- update docs and runbooks

## 14.2 Cutover Strategy

Preferred strategy:

- short maintenance-window cutover

Reason:

- this app already has a simple persistence layer
- dual-write would add complexity and risk disproportionate to current scope
- preserving correctness is more important than chasing a no-downtime illusion

## 14.3 Rollback Strategy

Rollback must be defined before production cutover.

Rollback plan:

1. keep the final pre-cutover SQLite backup
2. deployable app version must exist for the old SQLite code path until cutover is validated
3. if critical defects appear after cutover, revert app configuration and redeploy prior version
4. preserve PostgreSQL state for investigation; do not destroy evidence during rollback

Important:

- if production allows writes after cutover, rollback becomes a data-reconciliation problem
- this is another reason to prefer a controlled maintenance window

## 15. Testing Plan

## 15.1 Required Automated Tests

- unit tests for repository methods
- migration tests for Alembic upgrade path
- data import tests using a representative SQLite fixture
- API-level integration tests against PostgreSQL

## 15.2 Critical Scenarios

- create and list saved results
- fetch saved result by ID
- create and reuse cached comparison
- create and fetch rank reports by `run_ids_key`
- create and fetch stakeholder reports
- user creation on first access
- plan change resets correct counters
- API call limit behavior under sequential and concurrent requests
- email limit behavior under sequential and concurrent requests
- token usage accumulation and monthly reset

## 15.3 Performance Validation

Before and after migration, measure:

- p50/p95 latency for list endpoints
- latency for create/read flows touching saved artifacts
- throughput under concurrent usage-counter updates
- connection pool behavior under load

The purpose is not to prove ORM speedups. It is to verify that the new stack behaves correctly and does not regress critical paths.

## 16. Operational Requirements

## 16.1 Backups

Production database backups must rely on managed Postgres backup facilities, not container file copies.

## 16.2 Observability

Add or confirm:

- DB connection error logging
- migration execution logging
- slow-query visibility where feasible
- health checks that validate app liveness without requiring schema mutation

## 16.3 Runbook Changes

Update the deployment runbook to replace:

- SQLite volume instructions
- SQLite backup/restore instructions
- `DB_PATH` references

With:

- Alembic migration commands
- PostgreSQL connection configuration
- managed backup/restore guidance
- connection troubleshooting guidance

## 17. Risks

## 17.1 Data Quality Risk

Risk:

- malformed JSON strings in SQLite may fail import into JSONB columns

Mitigation:

- preflight validation script before cutover
- explicit migration logs with row identifiers

## 17.2 Concurrency Behavior Risk

Risk:

- counter semantics may behave differently once concurrent requests become common

Mitigation:

- transaction-aware repository methods
- concurrency-focused tests

## 17.3 Timestamp Semantics Risk

Risk:

- current text timestamps may include formatting inconsistencies

Mitigation:

- normalize to UTC during import
- validate parse success before production cutover

## 17.4 Hidden Coupling Risk

Risk:

- some application logic may rely on current `sqlite3.Row` or text-JSON edge behavior

Mitigation:

- keep helper return shapes stable in phase 1
- add regression tests around repository outputs

## 18. Acceptance Criteria

This migration is complete only when all of the following are true:

- the app no longer depends on a local SQLite file in production
- the app reads and writes through PostgreSQL
- schema creation and evolution are handled by Alembic
- the startup path no longer performs schema mutations
- current saved artifacts and usage counters are preserved
- critical endpoints behave the same from the caller perspective
- the app can run across multiple instances against the same database
- indexes exist for current dominant query paths
- deployment/runbook documentation is updated

## 19. Recommended Deliverables

- SQLAlchemy database package
- Alembic configuration and migration environment
- initial PostgreSQL baseline migration
- SQLite-to-Postgres import script
- refactored persistence layer replacing raw `sqlite3`
- regression tests for persistence behavior
- updated deployment and operations documentation

## 20. Decisions Locked By This Spec

- PostgreSQL is the target production database.
- SQLAlchemy is the target Python database layer.
- Alembic is the only supported schema migration mechanism.
- JSON payloads move to `JSONB`.
- IDs are preserved during data migration.
- Phase 1 prioritizes compatibility and correctness over aggressive schema redesign.
- A controlled maintenance-window cutover is preferred over dual-write complexity.

## 21. Follow-Up Spec Candidates

These items are intentionally deferred unless they become necessary during implementation:

- canonical comparison key model for unordered run pairs
- converting polymorphic `source_type/source_id` into a more normalized reference strategy
- introducing dedicated user table ownership instead of Clerk-only external identity
- adding background jobs for long-running report generation
- switching from sync SQLAlchemy to async SQLAlchemy
