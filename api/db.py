from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import Text, and_, cast, delete, func, or_, select, update
from sqlalchemy.orm import Session

from database.models import SavedComparison, SavedRankReport, SavedResult, SavedStakeholderReport, UserUsage
from database.session import get_session, session_scope, verify_database_connection

TOKEN_LIMIT_FREE = int(os.getenv("TOKEN_LIMIT_FREE", "50000"))
TOKEN_LIMIT_PREMIUM = int(os.getenv("TOKEN_LIMIT_PREMIUM", "500000"))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _current_month() -> str:
    return _utcnow().strftime("%Y-%m")


def _current_day() -> date:
    return _utcnow().date()


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _normalize_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _normalize_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _month_changed(user: UserUsage) -> bool:
    current_month = _current_month()
    if user.tokens_last_reset_month != current_month:
        user.total_tokens = 0
        user.tokens_last_reset_month = current_month
        user.updated_at = _utcnow()
        return True
    return False


def _get_usage_user(session: Session, user_id: str, for_update: bool = False) -> UserUsage | None:
    stmt = select(UserUsage).where(UserUsage.user_id == user_id)
    if for_update:
        stmt = stmt.with_for_update()
    return session.execute(stmt).scalar_one_or_none()


def _serialize_saved_result(row: SavedResult, include_full: bool = False) -> dict[str, Any]:
    models = _normalize_list(row.models_json)
    constraints = _normalize_list(row.constraints_json)
    payload = {
        "id": row.id,
        "created_at": _isoformat(row.created_at),
        "industry": row.industry,
        "tone": row.tone,
        "constraints": constraints,
        "models": models,
    }
    if include_full:
        payload["results"] = _normalize_dict(row.results_json)
        payload["rank_result"] = row.rank_result_json if isinstance(row.rank_result_json, dict) else None
    else:
        payload["model_count"] = len(models)
    return payload


def _serialize_rank_report(row: SavedRankReport) -> dict[str, Any]:
    run_ids = _normalize_list(row.run_ids_json)
    runs_snapshot = _normalize_list(row.runs_json)
    if not run_ids and runs_snapshot:
        recovered_ids: list[int] = []
        for run in runs_snapshot:
            if isinstance(run, dict):
                try:
                    recovered_ids.append(int(run.get("id")))
                except (TypeError, ValueError):
                    continue
        run_ids = recovered_ids
    cleaned_run_ids: list[int] = []
    for run_id in run_ids:
        try:
            cleaned_run_ids.append(int(run_id))
        except (TypeError, ValueError):
            continue
    return {
        "id": row.id,
        "created_at": _isoformat(row.created_at),
        "run_ids": cleaned_run_ids,
        "run_ids_key": row.run_ids_key,
        "report": _normalize_dict(row.report_json),
        "runs_snapshot": runs_snapshot,
        "model": row.model,
    }


def _serialize_comparison(row: SavedComparison) -> dict[str, Any]:
    return {
        "comparison_id": row.id,
        "created_at": _isoformat(row.created_at),
        "run_a_id": row.run_a_id,
        "run_b_id": row.run_b_id,
        "winner_run_id": row.winner_run_id,
        "comparison": _normalize_dict(row.comparison_json),
        "cached": True,
    }


def _serialize_stakeholder_report(row: SavedStakeholderReport) -> dict[str, Any]:
    return {
        "id": row.id,
        "created_at": _isoformat(row.created_at),
        "source_type": row.source_type,
        "source_id": row.source_id,
        "scenario_profile": row.scenario_profile,
        "horizon_months": row.horizon_months,
        "currency": row.currency,
        "region": row.region,
        "model": row.model,
        "assumptions": _normalize_list(row.assumptions_json),
        "dossier": _normalize_dict(row.dossier_json),
    }


def get_db() -> Session:
    return get_session()


def init_db() -> None:
    verify_database_connection()


def ensure_user(user_id: str, current_plan: str) -> None:
    with session_scope() as session:
        with session.begin():
            get_or_create_user(session, user_id, current_plan, for_update=True)


def get_or_create_user(conn: Session, user_id: str, current_plan: str, for_update: bool = False) -> UserUsage:
    user = _get_usage_user(conn, user_id, for_update=for_update)
    if user is None:
        now = _utcnow()
        user = UserUsage(
            user_id=user_id,
            plan=current_plan,
            total_tokens=0,
            api_calls_count=0,
            api_window_start=now,
            emails_sent_count=0,
            emails_last_sent_date=None,
            tokens_last_reset_month=now.strftime("%Y-%m"),
            created_at=now,
            updated_at=now,
        )
        conn.add(user)
        conn.flush()
        return user

    if user.plan != current_plan:
        user.plan = current_plan
        user.api_calls_count = 0
        user.emails_sent_count = 0
        user.updated_at = _utcnow()
        conn.flush()
    return user


def get_user(conn: Session, user_id: str) -> UserUsage | None:
    return _get_usage_user(conn, user_id)


def get_token_limit(plan: str) -> int:
    return TOKEN_LIMIT_PREMIUM if "premium" in plan else TOKEN_LIMIT_FREE


def check_token_limit(user_id: str, plan: str) -> tuple[bool, str | None]:
    with session_scope() as session:
        with session.begin():
            user = get_or_create_user(session, user_id, plan, for_update=True)
            total_tokens = user.total_tokens or 0
            did_reset, _ = _reset_tokens_if_new_month(session, user_id, user.tokens_last_reset_month)
            if did_reset:
                total_tokens = 0
            token_limit = get_token_limit(plan)
            if total_tokens >= token_limit:
                return False, f"Monthly token limit exceeded. Limit: {token_limit} tokens."
            return True, None


def _reset_tokens_if_new_month(conn: Session, user_id: str, last_month: str) -> tuple[bool, str]:
    current_month = _current_month()
    if last_month != current_month:
        user = _get_usage_user(conn, user_id, for_update=True)
        if user is not None:
            user.total_tokens = 0
            user.tokens_last_reset_month = current_month
            user.updated_at = _utcnow()
            conn.flush()
        return True, current_month
    return False, current_month


def check_and_increment_api_call(user_id: str, plan: str) -> tuple[bool, str | None]:
    with session_scope() as session:
        with session.begin():
            user = get_or_create_user(session, user_id, plan, for_update=True)
            total_tokens = user.total_tokens or 0
            if _month_changed(user):
                total_tokens = 0

            token_limit = get_token_limit(plan)
            if total_tokens >= token_limit:
                return False, f"Monthly token limit exceeded. Limit: {token_limit} tokens."

            limit = 5 if "premium" in plan else 1
            now = _utcnow()
            window_start = user.api_window_start
            count = user.api_calls_count

            if (now - window_start).total_seconds() > 60:
                count = 0
                user.api_calls_count = 0
                user.api_window_start = now

            if count >= limit:
                return False, f"API rate limit exceeded. Limit: {limit}/min."

            user.api_calls_count += 1
            user.updated_at = now
            return True, None


def check_and_increment_email(user_id: str, plan: str) -> tuple[bool, str | None]:
    with session_scope() as session:
        with session.begin():
            user = get_or_create_user(session, user_id, plan, for_update=True)
            limit = 10 if "premium" in plan else 0
            if limit == 0:
                return False, "Email sending is a Premium feature."

            today = _current_day()
            count = user.emails_sent_count
            if user.emails_last_sent_date != today:
                count = 0
                user.emails_sent_count = 0
                user.emails_last_sent_date = today

            if count >= limit:
                return False, f"Daily email limit exceeded. Limit: {limit}/day."

            user.emails_sent_count += 1
            user.emails_last_sent_date = today
            user.updated_at = _utcnow()
            return True, None


def track_token_usage(user_id: str, tokens: int) -> None:
    with session_scope() as session:
        with session.begin():
            user = _get_usage_user(session, user_id, for_update=True)
            if user is None:
                return
            current_month = _current_month()
            if user.tokens_last_reset_month != current_month:
                user.total_tokens = tokens
                user.tokens_last_reset_month = current_month
            else:
                user.total_tokens += tokens
            user.updated_at = _utcnow()


def get_user_stats(user_id: str) -> dict[str, int]:
    with session_scope() as session:
        with session.begin():
            user = _get_usage_user(session, user_id, for_update=True)
            if not user:
                return {"total_tokens": 0, "api_calls_count": 0, "emails_sent_count": 0}

            total_tokens = user.total_tokens or 0
            if _month_changed(user):
                total_tokens = 0

            now = _utcnow()
            api_count = user.api_calls_count
            if (now - user.api_window_start).total_seconds() > 60 and api_count > 0:
                user.api_calls_count = 0
                user.api_window_start = now
                user.updated_at = now
                api_count = 0

            return {
                "total_tokens": int(total_tokens),
                "api_calls_count": int(api_count),
                "emails_sent_count": int(user.emails_sent_count or 0),
            }


def save_results(user_id: str, industry: str, tone: str, constraints: Any, models: Any, results: Any, rank_result: Any = None):
    with session_scope() as session:
        with session.begin():
            created_at = _utcnow()
            row = SavedResult(
                user_id=user_id,
                created_at=created_at,
                industry=industry,
                tone=tone,
                constraints_json=_normalize_list(constraints),
                models_json=_normalize_list(models),
                results_json=_normalize_dict(results),
                rank_result_json=rank_result if isinstance(rank_result, dict) else rank_result,
            )
            session.add(row)
            session.flush()
            return {"id": row.id, "created_at": _isoformat(created_at)}


def list_saved_results(user_id: str, limit: int = 10) -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.execute(
            select(SavedResult)
            .where(SavedResult.user_id == user_id)
            .order_by(SavedResult.created_at.desc())
            .limit(limit)
        ).scalars()
        return [_serialize_saved_result(row, include_full=False) for row in rows]


def list_saved_results_full(user_id: str, limit: int | None = None) -> list[dict[str, Any]]:
    with session_scope() as session:
        stmt = (
            select(SavedResult)
            .where(SavedResult.user_id == user_id)
            .order_by(SavedResult.created_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = session.execute(stmt).scalars()
        return [_serialize_saved_result(row, include_full=True) for row in rows]


def get_saved_result(user_id: str, saved_id: int) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.execute(
            select(SavedResult).where(and_(SavedResult.id == saved_id, SavedResult.user_id == user_id))
        ).scalar_one_or_none()
        if row is None:
            return None
        return _serialize_saved_result(row, include_full=True)


def get_saved_rank_report(user_id: str, run_ids_key: str) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.execute(
            select(SavedRankReport)
            .where(and_(SavedRankReport.user_id == user_id, SavedRankReport.run_ids_key == run_ids_key))
            .order_by(SavedRankReport.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            return None
        return _serialize_rank_report(row)


def save_rank_report(user_id: str, run_ids_key: str, run_ids: Any, report: Any, model: str, runs_snapshot: Any = None):
    with session_scope() as session:
        with session.begin():
            created_at = _utcnow()
            row = SavedRankReport(
                user_id=user_id,
                created_at=created_at,
                run_ids_key=run_ids_key,
                run_ids_json=_normalize_list(run_ids),
                report_json=_normalize_dict(report),
                runs_json=_normalize_list(runs_snapshot),
                model=model,
            )
            session.add(row)
            session.flush()
            return {"id": row.id, "created_at": _isoformat(created_at)}


def get_saved_rank_report_by_id(user_id: str, report_id: int) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.execute(
            select(SavedRankReport).where(and_(SavedRankReport.user_id == user_id, SavedRankReport.id == report_id))
        ).scalar_one_or_none()
        if row is None:
            return None
        return _serialize_rank_report(row)


def delete_saved_rank_report(user_id: str, report_id: int) -> bool:
    with session_scope() as session:
        with session.begin():
            result = session.execute(
                delete(SavedRankReport).where(and_(SavedRankReport.user_id == user_id, SavedRankReport.id == report_id))
            )
            return (result.rowcount or 0) > 0


def delete_all_saved_rank_reports(user_id: str) -> int:
    with session_scope() as session:
        with session.begin():
            result = session.execute(delete(SavedRankReport).where(SavedRankReport.user_id == user_id))
            return result.rowcount or 0


def list_saved_rank_reports(user_id: str, limit: int = 6) -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.execute(
            select(SavedRankReport)
            .where(SavedRankReport.user_id == user_id)
            .order_by(SavedRankReport.created_at.desc())
            .limit(limit)
        ).scalars()
        out: list[dict[str, Any]] = []
        for row in rows:
            serialized = _serialize_rank_report(row)
            report = serialized["report"]
            summary = str(report.get("summary", "") or "")
            ranked_runs = report.get("ranked_runs", []) or []
            top_run_id = None
            if isinstance(ranked_runs, list) and ranked_runs:
                try:
                    top_run_id = int(ranked_runs[0].get("run_id"))
                except (AttributeError, TypeError, ValueError):
                    top_run_id = None
            out.append(
                {
                    "id": serialized["id"],
                    "created_at": serialized["created_at"],
                    "run_ids": serialized["run_ids"],
                    "summary": summary,
                    "top_run_id": top_run_id,
                    "model": serialized["model"],
                }
            )
        return out


def update_rank_report_snapshot(user_id: str, report_id: int, runs_snapshot: Any = None) -> bool:
    if runs_snapshot is None:
        return False
    with session_scope() as session:
        with session.begin():
            result = session.execute(
                update(SavedRankReport)
                .where(and_(SavedRankReport.user_id == user_id, SavedRankReport.id == report_id))
                .values(runs_json=_normalize_list(runs_snapshot))
            )
            return (result.rowcount or 0) > 0


def get_saved_results_by_ids(user_id: str, ids: list[int]) -> list[dict[str, Any]]:
    if not ids:
        return []
    with session_scope() as session:
        rows = session.execute(
            select(SavedResult).where(and_(SavedResult.user_id == user_id, SavedResult.id.in_(ids)))
        ).scalars()
        by_id = {row.id: _serialize_saved_result(row, include_full=True) for row in rows}
        return [by_id[result_id] for result_id in ids if result_id in by_id]


def get_saved_comparison(user_id: str, run_a_id: int, run_b_id: int) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.execute(
            select(SavedComparison)
            .where(
                and_(
                    SavedComparison.user_id == user_id,
                    or_(
                        and_(SavedComparison.run_a_id == run_a_id, SavedComparison.run_b_id == run_b_id),
                        and_(SavedComparison.run_a_id == run_b_id, SavedComparison.run_b_id == run_a_id),
                    ),
                )
            )
            .order_by(SavedComparison.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            return None
        payload = _serialize_comparison(row)
        winner_run_id = row.winner_run_id
        if winner_run_id == run_a_id:
            winner = "A"
        elif winner_run_id == run_b_id:
            winner = "B"
        else:
            winner = "tie"
        payload["comparison"]["winner"] = winner
        return payload


def get_saved_comparison_by_id(user_id: str, comparison_id: int) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.execute(
            select(SavedComparison).where(
                and_(SavedComparison.user_id == user_id, SavedComparison.id == comparison_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return _serialize_comparison(row)


def delete_saved_comparison(user_id: str, comparison_id: int) -> bool:
    with session_scope() as session:
        with session.begin():
            result = session.execute(
                delete(SavedComparison).where(
                    and_(SavedComparison.user_id == user_id, SavedComparison.id == comparison_id)
                )
            )
            return (result.rowcount or 0) > 0


def delete_all_saved_comparisons(user_id: str) -> int:
    with session_scope() as session:
        with session.begin():
            result = session.execute(delete(SavedComparison).where(SavedComparison.user_id == user_id))
            return result.rowcount or 0


def save_comparison(user_id: str, run_a_id: int, run_b_id: int, winner_run_id: int | None, comparison: Any, model: str):
    with session_scope() as session:
        with session.begin():
            created_at = _utcnow()
            row = SavedComparison(
                user_id=user_id,
                created_at=created_at,
                run_a_id=run_a_id,
                run_b_id=run_b_id,
                winner_run_id=winner_run_id,
                comparison_json=_normalize_dict(comparison),
                model=model,
            )
            session.add(row)
            session.flush()
            return {"id": row.id, "created_at": _isoformat(created_at)}


def list_saved_comparisons(user_id: str, limit: int = 8) -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.execute(
            select(SavedComparison)
            .where(SavedComparison.user_id == user_id)
            .order_by(SavedComparison.created_at.desc())
            .limit(limit)
        ).scalars()
        out: list[dict[str, Any]] = []
        for row in rows:
            comparison = _normalize_dict(row.comparison_json)
            out.append(
                {
                    "id": row.id,
                    "created_at": _isoformat(row.created_at),
                    "run_a_id": row.run_a_id,
                    "run_b_id": row.run_b_id,
                    "winner_run_id": row.winner_run_id,
                    "top_outputs": comparison.get("top_outputs"),
                }
            )
        return out


def delete_saved_result(user_id: str, saved_id: int) -> bool:
    with session_scope() as session:
        with session.begin():
            result = session.execute(
                delete(SavedResult).where(and_(SavedResult.id == saved_id, SavedResult.user_id == user_id))
            )
            return (result.rowcount or 0) > 0


def delete_all_saved_results(user_id: str) -> int:
    with session_scope() as session:
        with session.begin():
            result = session.execute(delete(SavedResult).where(SavedResult.user_id == user_id))
            return result.rowcount or 0


def update_saved_result_rank(user_id: str, saved_id: int, rank_result: Any) -> bool:
    with session_scope() as session:
        with session.begin():
            result = session.execute(
                update(SavedResult)
                .where(and_(SavedResult.id == saved_id, SavedResult.user_id == user_id))
                .values(rank_result_json=rank_result if isinstance(rank_result, dict) else {})
            )
            return (result.rowcount or 0) > 0


def get_saved_results_usage_bytes(user_id: str) -> int:
    with session_scope() as session:
        total_expr = func.coalesce(
            func.sum(
                func.length(func.coalesce(SavedResult.industry, ""))
                + func.length(func.coalesce(SavedResult.tone, ""))
                + func.length(func.coalesce(cast(SavedResult.constraints_json, Text), ""))
                + func.length(func.coalesce(cast(SavedResult.models_json, Text), ""))
                + func.length(func.coalesce(cast(SavedResult.results_json, Text), ""))
                + func.length(func.coalesce(cast(SavedResult.rank_result_json, Text), ""))
            ),
            0,
        )
        total = session.execute(select(total_expr).where(SavedResult.user_id == user_id)).scalar_one()
        return int(total or 0)


def save_stakeholder_report(
    user_id: str,
    source_type: str,
    source_id: int,
    scenario_profile: str,
    horizon_months: int,
    currency: str,
    region: str,
    dossier: Any,
    assumptions: Any,
    model: str | None = None,
):
    with session_scope() as session:
        with session.begin():
            created_at = _utcnow()
            row = SavedStakeholderReport(
                user_id=user_id,
                created_at=created_at,
                source_type=source_type,
                source_id=source_id,
                scenario_profile=scenario_profile,
                horizon_months=horizon_months,
                currency=currency,
                region=region,
                dossier_json=_normalize_dict(dossier),
                assumptions_json=_normalize_list(assumptions),
                model=model,
            )
            session.add(row)
            session.flush()
            return {"id": row.id, "created_at": _isoformat(created_at)}


def get_saved_stakeholder_report_by_id(user_id: str, report_id: int) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.execute(
            select(SavedStakeholderReport).where(
                and_(SavedStakeholderReport.user_id == user_id, SavedStakeholderReport.id == report_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return _serialize_stakeholder_report(row)


def list_saved_stakeholder_reports(user_id: str, limit: int = 6) -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.execute(
            select(SavedStakeholderReport)
            .where(SavedStakeholderReport.user_id == user_id)
            .order_by(SavedStakeholderReport.created_at.desc())
            .limit(limit)
        ).scalars()
        out: list[dict[str, Any]] = []
        for row in rows:
            dossier = _normalize_dict(row.dossier_json)
            title = "Untitled execution plan"
            recommendation = "conditional_go"
            decision = dossier.get("decision") if isinstance(dossier.get("decision"), dict) else {}
            winner = decision.get("winner") if isinstance(decision.get("winner"), dict) else {}
            winner_title = str(winner.get("title") or "").strip()
            if winner_title:
                title = winner_title
            raw_recommendation = str(decision.get("go_no_go") or "").strip().lower()
            if raw_recommendation in {"go", "conditional_go", "no_go"}:
                recommendation = raw_recommendation
            out.append(
                {
                    "id": row.id,
                    "created_at": _isoformat(row.created_at),
                    "source_type": row.source_type,
                    "source_id": row.source_id,
                    "scenario_profile": row.scenario_profile,
                    "horizon_months": row.horizon_months,
                    "currency": row.currency,
                    "region": row.region,
                    "model": row.model,
                    "title": title,
                    "recommendation": recommendation,
                }
            )
        return out


def delete_saved_stakeholder_report(user_id: str, report_id: int) -> bool:
    with session_scope() as session:
        with session.begin():
            result = session.execute(
                delete(SavedStakeholderReport).where(
                    and_(SavedStakeholderReport.user_id == user_id, SavedStakeholderReport.id == report_id)
                )
            )
            return (result.rowcount or 0) > 0


def delete_all_saved_stakeholder_reports(user_id: str) -> int:
    with session_scope() as session:
        with session.begin():
            result = session.execute(
                delete(SavedStakeholderReport).where(SavedStakeholderReport.user_id == user_id)
            )
            return result.rowcount or 0
