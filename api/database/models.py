from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, Identity, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class UserUsage(Base):
    __tablename__ = "user_usage"

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    plan: Mapped[str] = mapped_column(Text, nullable=False)
    total_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    api_calls_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    api_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    emails_sent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    emails_last_sent_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    tokens_last_reset_month: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("total_tokens >= 0", name="ck_user_usage_total_tokens_nonnegative"),
        CheckConstraint("api_calls_count >= 0", name="ck_user_usage_api_calls_nonnegative"),
        CheckConstraint("emails_sent_count >= 0", name="ck_user_usage_emails_nonnegative"),
    )


class SavedResult(Base):
    __tablename__ = "saved_results"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    industry: Mapped[str | None] = mapped_column(Text, nullable=True)
    tone: Mapped[str | None] = mapped_column(Text, nullable=True)
    constraints_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    models_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    results_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    rank_result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("idx_saved_results_user_created_at", "user_id", "created_at"),
        Index("idx_saved_results_user_id_id", "user_id", "id"),
    )


class SavedRankReport(Base):
    __tablename__ = "saved_rank_reports"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    run_ids_key: Mapped[str] = mapped_column(Text, nullable=False)
    run_ids_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    report_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    runs_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_saved_rank_reports_user_created_at", "user_id", "created_at"),
        Index("idx_saved_rank_reports_user_run_ids_key_created_at", "user_id", "run_ids_key", "created_at"),
    )


class SavedComparison(Base):
    __tablename__ = "saved_comparisons"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    run_a_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    run_b_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    winner_run_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    comparison_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_saved_comparisons_user_created_at", "user_id", "created_at"),
        Index("idx_saved_comparisons_user_runs_created_at", "user_id", "run_a_id", "run_b_id", "created_at"),
    )


class SavedStakeholderReport(Base):
    __tablename__ = "saved_stakeholder_reports"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    scenario_profile: Mapped[str | None] = mapped_column(Text, nullable=True)
    horizon_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(Text, nullable=True)
    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    dossier_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    assumptions_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "source_type IN ('decision_report', 'compare_result', 'saved_run')",
            name="ck_saved_stakeholder_reports_source_type",
        ),
        Index("idx_saved_stakeholder_reports_user_created_at", "user_id", "created_at"),
        Index(
            "idx_saved_stakeholder_reports_user_source_created_at",
            "user_id",
            "source_type",
            "source_id",
            "created_at",
        ),
    )
