from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, text

import sys

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from database.models import SavedComparison, SavedRankReport, SavedResult, SavedStakeholderReport, UserUsage  # noqa: E402
from database.session import session_scope  # noqa: E402


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if value in (None, ""):
        return datetime.now(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    raise ValueError(f"Unsupported datetime value: {value!r}")


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError(f"Unsupported date value: {value!r}")


def _parse_json(value: Any, default: Any, *, table: str, column: str, row_id: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{table}.{column} row={row_id} contains invalid JSON") from exc
    raise ValueError(f"{table}.{column} row={row_id} contains unsupported JSON value {value!r}")


def _sqlite_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def _sqlite_rows(conn: sqlite3.Connection, table_name: str) -> list[sqlite3.Row]:
    return conn.execute(f"SELECT * FROM {table_name}").fetchall()


def _truncate_target(session) -> None:
    session.execute(delete(SavedStakeholderReport))
    session.execute(delete(SavedComparison))
    session.execute(delete(SavedRankReport))
    session.execute(delete(SavedResult))
    session.execute(delete(UserUsage))


def _ensure_empty_target(session) -> None:
    existing = {
        "user_usage": session.execute(select(func.count()).select_from(UserUsage)).scalar_one(),
        "saved_results": session.execute(select(func.count()).select_from(SavedResult)).scalar_one(),
        "saved_rank_reports": session.execute(select(func.count()).select_from(SavedRankReport)).scalar_one(),
        "saved_comparisons": session.execute(select(func.count()).select_from(SavedComparison)).scalar_one(),
        "saved_stakeholder_reports": session.execute(select(func.count()).select_from(SavedStakeholderReport)).scalar_one(),
    }
    if any(existing.values()):
        raise RuntimeError(f"Target PostgreSQL database is not empty: {existing}")


def _set_sequence(session, table_name: str) -> None:
    session.execute(
        text(
            f"""
            SELECT setval(
                pg_get_serial_sequence('{table_name}', 'id'),
                COALESCE((SELECT MAX(id) FROM {table_name}), 1),
                (SELECT COUNT(*) > 0 FROM {table_name})
            )
            """
        )
    )


def import_sqlite_to_postgres(sqlite_path: str, truncate: bool = False) -> dict[str, Any]:
    sqlite_file = Path(sqlite_path)
    if not sqlite_file.exists():
        raise FileNotFoundError(f"SQLite source not found: {sqlite_file}")

    source = sqlite3.connect(str(sqlite_file))
    source.row_factory = sqlite3.Row

    try:
        source_columns = {
            "user_usage": _sqlite_columns(source, "user_usage"),
            "saved_results": _sqlite_columns(source, "saved_results"),
            "saved_rank_reports": _sqlite_columns(source, "saved_rank_reports"),
            "saved_comparisons": _sqlite_columns(source, "saved_comparisons"),
            "saved_stakeholder_reports": _sqlite_columns(source, "saved_stakeholder_reports"),
        }
        source_counts = {table: len(_sqlite_rows(source, table)) for table in source_columns}

        with session_scope() as session:
            with session.begin():
                if truncate:
                    _truncate_target(session)
                else:
                    _ensure_empty_target(session)

                now = datetime.now(timezone.utc)

                for row in _sqlite_rows(source, "user_usage"):
                    session.add(
                        UserUsage(
                            user_id=row["user_id"],
                            plan=row["plan"] or "u:free_user",
                            total_tokens=int(row["total_tokens"] or 0),
                            api_calls_count=int(row["api_calls_count"] or 0),
                            api_window_start=_parse_datetime(row["api_window_start"] or 0),
                            emails_sent_count=int(row["emails_sent_count"] or 0),
                            emails_last_sent_date=_parse_date(row["emails_last_sent_date"]),
                            tokens_last_reset_month=row["tokens_last_reset_date"] or now.strftime("%Y-%m"),
                            created_at=now,
                            updated_at=now,
                        )
                    )

                for row in _sqlite_rows(source, "saved_results"):
                    session.add(
                        SavedResult(
                            id=int(row["id"]),
                            user_id=row["user_id"],
                            created_at=_parse_datetime(row["created_at"]),
                            industry=row["industry"],
                            tone=row["tone"],
                            constraints_json=_parse_json(
                                row["constraints_json"], [], table="saved_results", column="constraints_json", row_id=row["id"]
                            ),
                            models_json=_parse_json(
                                row["models_json"], [], table="saved_results", column="models_json", row_id=row["id"]
                            ),
                            results_json=_parse_json(
                                row["results_json"], {}, table="saved_results", column="results_json", row_id=row["id"]
                            ),
                            rank_result_json=_parse_json(
                                row["rank_result_json"] if "rank_result_json" in source_columns["saved_results"] else None,
                                None,
                                table="saved_results",
                                column="rank_result_json",
                                row_id=row["id"],
                            ),
                        )
                    )

                for row in _sqlite_rows(source, "saved_rank_reports"):
                    session.add(
                        SavedRankReport(
                            id=int(row["id"]),
                            user_id=row["user_id"],
                            created_at=_parse_datetime(row["created_at"]),
                            run_ids_key=row["run_ids_key"],
                            run_ids_json=_parse_json(
                                row["run_ids_json"], [], table="saved_rank_reports", column="run_ids_json", row_id=row["id"]
                            ),
                            report_json=_parse_json(
                                row["report_json"], {}, table="saved_rank_reports", column="report_json", row_id=row["id"]
                            ),
                            runs_json=_parse_json(
                                row["runs_json"] if "runs_json" in source_columns["saved_rank_reports"] else None,
                                [],
                                table="saved_rank_reports",
                                column="runs_json",
                                row_id=row["id"],
                            ),
                            model=row["model"],
                        )
                    )

                for row in _sqlite_rows(source, "saved_comparisons"):
                    session.add(
                        SavedComparison(
                            id=int(row["id"]),
                            user_id=row["user_id"],
                            created_at=_parse_datetime(row["created_at"]),
                            run_a_id=int(row["run_a_id"]),
                            run_b_id=int(row["run_b_id"]),
                            winner_run_id=int(row["winner_run_id"]) if row["winner_run_id"] is not None else None,
                            comparison_json=_parse_json(
                                row["comparison_json"], {}, table="saved_comparisons", column="comparison_json", row_id=row["id"]
                            ),
                            model=row["model"],
                        )
                    )

                for row in _sqlite_rows(source, "saved_stakeholder_reports"):
                    session.add(
                        SavedStakeholderReport(
                            id=int(row["id"]),
                            user_id=row["user_id"],
                            created_at=_parse_datetime(row["created_at"]),
                            source_type=row["source_type"],
                            source_id=int(row["source_id"]),
                            scenario_profile=row["scenario_profile"],
                            horizon_months=int(row["horizon_months"]) if row["horizon_months"] is not None else None,
                            currency=row["currency"],
                            region=row["region"],
                            dossier_json=_parse_json(
                                row["dossier_json"], {}, table="saved_stakeholder_reports", column="dossier_json", row_id=row["id"]
                            ),
                            assumptions_json=_parse_json(
                                row["assumptions_json"],
                                [],
                                table="saved_stakeholder_reports",
                                column="assumptions_json",
                                row_id=row["id"],
                            ),
                            model=row["model"] if "model" in source_columns["saved_stakeholder_reports"] else None,
                        )
                    )

                session.flush()
                for table_name in (
                    "saved_results",
                    "saved_rank_reports",
                    "saved_comparisons",
                    "saved_stakeholder_reports",
                ):
                    _set_sequence(session, table_name)

            target_counts = {
                "user_usage": session.execute(select(func.count()).select_from(UserUsage)).scalar_one(),
                "saved_results": session.execute(select(func.count()).select_from(SavedResult)).scalar_one(),
                "saved_rank_reports": session.execute(select(func.count()).select_from(SavedRankReport)).scalar_one(),
                "saved_comparisons": session.execute(select(func.count()).select_from(SavedComparison)).scalar_one(),
                "saved_stakeholder_reports": session.execute(select(func.count()).select_from(SavedStakeholderReport)).scalar_one(),
            }
    finally:
        source.close()

    return {
        "source_counts": source_counts,
        "target_counts": target_counts,
        "sqlite_path": str(sqlite_file),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import the existing SQLite database into PostgreSQL.")
    parser.add_argument("--sqlite-path", required=True, help="Path to the SQLite database file.")
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Delete all existing target rows before import.",
    )
    args = parser.parse_args()

    report = import_sqlite_to_postgres(args.sqlite_path, truncate=args.truncate)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
