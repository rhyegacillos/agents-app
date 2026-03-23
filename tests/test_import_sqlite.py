from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.import_sqlite_to_postgres import import_sqlite_to_postgres

import importlib


def _db():
    return importlib.import_module("db")


def _create_sqlite_fixture(path: Path, invalid_json: bool = False) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE user_usage (
                user_id TEXT PRIMARY KEY,
                plan TEXT,
                total_tokens INTEGER DEFAULT 0,
                api_calls_count INTEGER DEFAULT 0,
                api_window_start REAL DEFAULT 0,
                emails_sent_count INTEGER DEFAULT 0,
                emails_last_sent_date TEXT DEFAULT '',
                tokens_last_reset_date TEXT DEFAULT ''
            );
            CREATE TABLE saved_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                created_at TEXT,
                industry TEXT,
                tone TEXT,
                constraints_json TEXT,
                models_json TEXT,
                results_json TEXT,
                rank_result_json TEXT
            );
            CREATE TABLE saved_rank_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                created_at TEXT,
                run_ids_key TEXT,
                run_ids_json TEXT,
                report_json TEXT,
                runs_json TEXT,
                model TEXT
            );
            CREATE TABLE saved_comparisons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                created_at TEXT,
                run_a_id INTEGER,
                run_b_id INTEGER,
                winner_run_id INTEGER,
                comparison_json TEXT,
                model TEXT
            );
            CREATE TABLE saved_stakeholder_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                created_at TEXT,
                source_type TEXT,
                source_id INTEGER,
                scenario_profile TEXT,
                horizon_months INTEGER,
                currency TEXT,
                region TEXT,
                dossier_json TEXT,
                assumptions_json TEXT,
                model TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO user_usage (
                user_id, plan, total_tokens, api_calls_count, api_window_start, emails_sent_count,
                emails_last_sent_date, tokens_last_reset_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("import-user", "u:premium_user", 25, 1, 1710800000.0, 2, "2026-03-19", "2026-03"),
        )
        conn.execute(
            """
            INSERT INTO saved_results (
                id, user_id, created_at, industry, tone, constraints_json, models_json, results_json, rank_result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                11,
                "import-user",
                "2026-03-19T10:00:00+00:00",
                "AI",
                "Bold",
                '["A"]',
                '["m1"]',
                '{"idea":"A"}',
                '{"winner":"m1"}' if not invalid_json else "{bad json",
            ),
        )
        conn.execute(
            """
            INSERT INTO saved_rank_reports (
                id, user_id, created_at, run_ids_key, run_ids_json, report_json, runs_json, model
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                21,
                "import-user",
                "2026-03-19T11:00:00+00:00",
                "11",
                "[11]",
                '{"summary":"Imported"}',
                '[{"id":11}]',
                "gpt-5-mini",
            ),
        )
        conn.execute(
            """
            INSERT INTO saved_comparisons (
                id, user_id, created_at, run_a_id, run_b_id, winner_run_id, comparison_json, model
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                31,
                "import-user",
                "2026-03-19T12:00:00+00:00",
                11,
                11,
                11,
                '{"top_outputs":["A"]}',
                "gpt-5-mini",
            ),
        )
        conn.execute(
            """
            INSERT INTO saved_stakeholder_reports (
                id, user_id, created_at, source_type, source_id, scenario_profile, horizon_months,
                currency, region, dossier_json, assumptions_json, model
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                41,
                "import-user",
                "2026-03-19T13:00:00+00:00",
                "decision_report",
                21,
                "base",
                12,
                "USD",
                "US",
                '{"decision":{"winner":{"title":"Imported Run"},"go_no_go":"go"}}',
                '[{"name":"ARPU"}]',
                "gpt-5-mini",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_import_sqlite_to_postgres_preserves_data(migrated_db, tmp_path):
    sqlite_path = tmp_path / "usage.db"
    _create_sqlite_fixture(sqlite_path)

    report = import_sqlite_to_postgres(str(sqlite_path))

    assert report["source_counts"] == report["target_counts"]
    assert report["target_counts"]["saved_results"] == 1

    db = _db()
    imported = db.get_saved_result("import-user", 11)
    assert imported["industry"] == "AI"
    assert imported["rank_result"] == {"winner": "m1"}

    reports = db.list_saved_rank_reports("import-user", limit=5)
    assert reports[0]["summary"] == "Imported"

    stakeholder = db.get_saved_stakeholder_report_by_id("import-user", 41)
    assert stakeholder["dossier"]["decision"]["winner"]["title"] == "Imported Run"


def test_import_sqlite_to_postgres_rejects_invalid_json(migrated_db, tmp_path):
    sqlite_path = tmp_path / "bad.db"
    _create_sqlite_fixture(sqlite_path, invalid_json=True)

    with pytest.raises(ValueError, match="invalid JSON"):
        import_sqlite_to_postgres(str(sqlite_path))
