from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import importlib

from sqlalchemy import select


def _db():
    return importlib.import_module("db")


def _session_scope():
    return importlib.import_module("database.session").session_scope


def _models():
    return importlib.import_module("database.models")


def test_saved_results_contract_and_ordering(migrated_db):
    db = _db()

    first = db.save_results("user-1", "Fintech", "Bold", ["A"], ["m1"], {"x": 1})
    second = db.save_results("user-1", "Health", "Calm", ["B"], ["m2", "m3"], {"y": 2}, {"winner": "m2"})

    session_scope = _session_scope()
    models = _models()
    with session_scope() as session:
        first_row = session.execute(select(models.SavedResult).where(models.SavedResult.id == first["id"])).scalar_one()
        second_row = session.execute(select(models.SavedResult).where(models.SavedResult.id == second["id"])).scalar_one()
        first_row.created_at = datetime.now(timezone.utc) - timedelta(days=1)
        second_row.created_at = datetime.now(timezone.utc)
        session.commit()

    listed = db.list_saved_results("user-1", limit=10)
    assert [row["id"] for row in listed] == [second["id"], first["id"]]
    assert listed[0]["model_count"] == 2

    full = db.get_saved_result("user-1", second["id"])
    assert full["results"] == {"y": 2}
    assert full["rank_result"] == {"winner": "m2"}

    ordered_by_ids = db.get_saved_results_by_ids("user-1", [first["id"], second["id"]])
    assert [row["id"] for row in ordered_by_ids] == [first["id"], second["id"]]

    usage_bytes = db.get_saved_results_usage_bytes("user-1")
    assert usage_bytes > 0

    assert db.delete_saved_result("user-1", first["id"]) is True
    assert db.delete_saved_result("user-1", 999999) is False


def test_rank_reports_comparisons_and_stakeholder_reports_contract(migrated_db):
    db = _db()

    run_a = db.save_results("user-2", "AI", "Sharp", ["A"], ["m1"], {"idea": "A"})
    run_b = db.save_results("user-2", "AI", "Sharp", ["A"], ["m2"], {"idea": "B"})

    report = db.save_rank_report(
        "user-2",
        "1,2",
        [run_a["id"], run_b["id"]],
        {"summary": "Use run B", "ranked_runs": [{"run_id": run_b["id"]}]},
        "gpt-5-mini",
        runs_snapshot=[{"id": run_a["id"]}, {"id": run_b["id"]}],
    )
    fetched_report = db.get_saved_rank_report("user-2", "1,2")
    assert fetched_report["id"] == report["id"]
    assert fetched_report["run_ids"] == [run_a["id"], run_b["id"]]

    report_list = db.list_saved_rank_reports("user-2", limit=10)
    assert report_list[0]["top_run_id"] == run_b["id"]
    assert db.update_rank_report_snapshot("user-2", report["id"], [{"id": run_b["id"]}]) is True
    assert db.delete_saved_rank_report("user-2", 999999) is False

    comparison = db.save_comparison(
        "user-2",
        run_a["id"],
        run_b["id"],
        run_b["id"],
        {"top_outputs": ["B"], "winner": "B"},
        "gpt-5-mini",
    )
    cached = db.get_saved_comparison("user-2", run_b["id"], run_a["id"])
    assert cached["comparison_id"] == comparison["id"]
    assert cached["comparison"]["winner"] == "A"

    comparison_list = db.list_saved_comparisons("user-2", limit=10)
    assert comparison_list[0]["top_outputs"] == ["B"]

    stakeholder = db.save_stakeholder_report(
        "user-2",
        "decision_report",
        report["id"],
        "base",
        12,
        "USD",
        "US",
        {"decision": {"winner": {"title": "Run B"}, "go_no_go": "go"}},
        [{"name": "ARPU"}],
        model="gpt-5-mini",
    )
    stakeholder_row = db.get_saved_stakeholder_report_by_id("user-2", stakeholder["id"])
    assert stakeholder_row["dossier"]["decision"]["winner"]["title"] == "Run B"

    stakeholder_list = db.list_saved_stakeholder_reports("user-2", limit=10)
    assert stakeholder_list[0]["title"] == "Run B"
    assert stakeholder_list[0]["recommendation"] == "go"

    assert db.delete_saved_comparison("user-2", comparison["id"]) is True
    assert db.delete_saved_stakeholder_report("user-2", stakeholder["id"]) is True
    assert db.delete_all_saved_rank_reports("user-2") == 1


def test_usage_stats_and_reset_behaviors(migrated_db):
    db = _db()
    models = _models()
    session_scope = _session_scope()

    db.ensure_user("user-3", "u:premium_user")
    stats = db.get_user_stats("user-3")
    assert stats == {"total_tokens": 0, "api_calls_count": 0, "emails_sent_count": 0}

    db.track_token_usage("user-3", 120)
    stats = db.get_user_stats("user-3")
    assert stats["total_tokens"] == 120

    with session_scope() as session:
        user = session.execute(select(models.UserUsage).where(models.UserUsage.user_id == "user-3")).scalar_one()
        user.tokens_last_reset_month = "2000-01"
        user.api_calls_count = 3
        user.api_window_start = datetime.now(timezone.utc) - timedelta(seconds=120)
        user.emails_sent_count = 4
        user.emails_last_sent_date = date(2000, 1, 1)
        session.commit()

    stats = db.get_user_stats("user-3")
    assert stats["total_tokens"] == 0
    assert stats["api_calls_count"] == 0
    assert stats["emails_sent_count"] == 4

    for _ in range(5):
        allowed, _ = db.check_and_increment_api_call("user-3", "u:premium_user")
        assert allowed is True
    allowed, message = db.check_and_increment_api_call("user-3", "u:premium_user")
    assert allowed is False
    assert "5/min" in message

    for _ in range(10):
        allowed, _ = db.check_and_increment_email("user-3", "u:premium_user")
        assert allowed is True
    allowed, message = db.check_and_increment_email("user-3", "u:premium_user")
    assert allowed is False
    assert "10/day" in message


def test_plan_change_resets_api_and_email_counters(migrated_db):
    db = _db()
    models = _models()
    session_scope = _session_scope()

    db.ensure_user("user-4", "u:free_user")
    with session_scope() as session:
        user = session.execute(select(models.UserUsage).where(models.UserUsage.user_id == "user-4")).scalar_one()
        user.api_calls_count = 7
        user.emails_sent_count = 3
        session.commit()

    db.ensure_user("user-4", "u:premium_user")
    with session_scope() as session:
        user = session.execute(select(models.UserUsage).where(models.UserUsage.user_id == "user-4")).scalar_one()
        assert user.plan == "u:premium_user"
        assert user.api_calls_count == 0
        assert user.emails_sent_count == 0


def test_concurrent_usage_updates_are_safe(migrated_db):
    db = _db()
    db.ensure_user("user-5", "u:premium_user")

    def add_tokens():
        db.track_token_usage("user-5", 10)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: add_tokens(), range(20)))

    stats = db.get_user_stats("user-5")
    assert stats["total_tokens"] == 200


def test_concurrent_api_rate_limit_is_enforced(migrated_db):
    db = _db()
    db.ensure_user("user-6", "u:premium_user")

    def hit():
        return db.check_and_increment_api_call("user-6", "u:premium_user")[0]

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _: hit(), range(12)))

    assert sum(1 for item in results if item) == 5
    assert sum(1 for item in results if not item) == 7


def test_concurrent_email_limit_is_enforced(migrated_db):
    db = _db()
    db.ensure_user("user-7", "u:premium_user")

    def send_email():
        return db.check_and_increment_email("user-7", "u:premium_user")[0]

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: send_email(), range(16)))

    assert sum(1 for item in results if item) == 10
    assert sum(1 for item in results if not item) == 6
