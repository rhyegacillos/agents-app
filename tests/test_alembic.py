from __future__ import annotations

import os

from sqlalchemy import create_engine, inspect


def test_alembic_upgrade_creates_expected_schema(migrated_db):
    engine = create_engine(os.environ["DATABASE_URL_LOCAL"], future=True)
    inspector = inspect(engine)

    tables = set(inspector.get_table_names())
    assert {"alembic_version", "user_usage", "saved_results", "saved_rank_reports", "saved_comparisons", "saved_stakeholder_reports"} <= tables

    saved_results_columns = {column["name"] for column in inspector.get_columns("saved_results")}
    assert {"id", "user_id", "created_at", "constraints_json", "models_json", "results_json", "rank_result_json"} <= saved_results_columns

    stakeholder_indexes = {index["name"] for index in inspector.get_indexes("saved_stakeholder_reports")}
    assert "idx_saved_stakeholder_reports_user_created_at" in stakeholder_indexes
    assert "idx_saved_stakeholder_reports_user_source_created_at" in stakeholder_indexes

    engine.dispose()
