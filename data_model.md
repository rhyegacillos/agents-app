# Data Model / Schema

Database: SQLite
Path: `data/usage.db` (persisted via Docker volume `/app/data`)

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


## Tables

### user_usage
Stores usage counters and plan status per user.

Columns:
- `user_id` TEXT PRIMARY KEY
- `plan` TEXT
- `total_tokens` INTEGER
- `api_calls_count` INTEGER
- `api_window_start` REAL
- `emails_sent_count` INTEGER
- `emails_last_sent_date` TEXT
- `tokens_last_reset_date` TEXT

Relationships:
- One row per user (keyed by Clerk `sub`).

---

### saved_results
Stores generated runs for reuse.

Columns:
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `user_id` TEXT
- `created_at` TEXT
- `industry` TEXT
- `tone` TEXT
- `constraints_json` TEXT
- `models_json` TEXT
- `results_json` TEXT
- `rank_result_json` TEXT

Relationships:
- Many rows per user.
- Referenced by `saved_comparisons.run_a_id` and `saved_comparisons.run_b_id`.
- Referenced by `saved_rank_reports.run_ids_json`.

---

### saved_rank_reports
Stores Decision Summary Reports (ranked runs + summary).

Columns:
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `user_id` TEXT
- `created_at` TEXT
- `run_ids_key` TEXT
- `run_ids_json` TEXT
- `report_json` TEXT
- `runs_json` TEXT (snapshot of runs at report time)
- `model` TEXT

Relationships:
- `run_ids_json` references `saved_results.id` values.

---

### saved_comparisons
Stores Compare Results (Diff Insight) output.

Columns:
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `user_id` TEXT
- `created_at` TEXT
- `run_a_id` INTEGER
- `run_b_id` INTEGER
- `winner_run_id` INTEGER
- `comparison_json` TEXT
- `model` TEXT

Relationships:
- `run_a_id` and `run_b_id` reference `saved_results.id`.

---

### saved_stakeholder_reports
Stores Stakeholder Execution Dossiers (JSON artifact, no user input mode).

Columns:
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `user_id` TEXT
- `created_at` TEXT
- `source_type` TEXT (`decision_report`, `compare_result`, `saved_run`)
- `source_id` INTEGER
- `scenario_profile` TEXT (`conservative`, `base`, `aggressive`, `all`)
- `horizon_months` INTEGER
- `currency` TEXT (current: `USD`)
- `region` TEXT (current: `US`)
- `dossier_json` TEXT
- `assumptions_json` TEXT
- `model` TEXT

Relationships:
- `source_type/source_id` references one of:
  - `saved_rank_reports.id`
  - `saved_comparisons.id`
  - `saved_results.id`
- Relationship integrity is enforced in application logic.

Execution Plan payload conventions (stored inside `dossier_json`):
- `proposal_disclaimer`: marks report as benchmark-grounded estimate.
- `sensitivity_analysis`: ARPU / conversion / OpEx stress-test results.
- `decision_support`: gate status, required actions, and profitability recovery plan.
- `provenance.finance_mode`: `grounded_v2` (default) or `llm_v1`.
- `provenance.financials_grounded`: boolean indicating deterministic finance application.

---

## Migrations / Alterations
Applied at startup in `init_db()`:
- Add `tokens_last_reset_date` to `user_usage`.
- Add `rank_result_json` to `saved_results` (if missing).
- Add `runs_json` to `saved_rank_reports` (if missing).

## Notes
- JSON fields are stored as stringified JSON and parsed in `api/db.py`.
- There are no foreign key constraints; relationships are managed in application logic.
- `model` in `saved_stakeholder_reports` records the narrative model used; finance values may still be deterministic via `grounded_v2`.
