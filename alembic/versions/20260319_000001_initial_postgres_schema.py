"""initial postgres schema

Revision ID: 20260319_000001
Revises:
Create Date: 2026-03-19 00:00:01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260319_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_usage",
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("plan", sa.Text(), nullable=False),
        sa.Column("total_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("api_calls_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("api_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("emails_sent_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("emails_last_sent_date", sa.Date(), nullable=True),
        sa.Column("tokens_last_reset_month", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("total_tokens >= 0", name="ck_user_usage_total_tokens_nonnegative"),
        sa.CheckConstraint("api_calls_count >= 0", name="ck_user_usage_api_calls_nonnegative"),
        sa.CheckConstraint("emails_sent_count >= 0", name="ck_user_usage_emails_nonnegative"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "saved_results",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("industry", sa.Text(), nullable=True),
        sa.Column("tone", sa.Text(), nullable=True),
        sa.Column("constraints_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("models_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("results_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rank_result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_saved_results_user_created_at", "saved_results", ["user_id", "created_at"], unique=False)
    op.create_index("idx_saved_results_user_id_id", "saved_results", ["user_id", "id"], unique=False)

    op.create_table(
        "saved_rank_reports",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_ids_key", sa.Text(), nullable=False),
        sa.Column("run_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("runs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_saved_rank_reports_user_created_at",
        "saved_rank_reports",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_saved_rank_reports_user_run_ids_key_created_at",
        "saved_rank_reports",
        ["user_id", "run_ids_key", "created_at"],
        unique=False,
    )

    op.create_table(
        "saved_comparisons",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_a_id", sa.BigInteger(), nullable=False),
        sa.Column("run_b_id", sa.BigInteger(), nullable=False),
        sa.Column("winner_run_id", sa.BigInteger(), nullable=True),
        sa.Column("comparison_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_saved_comparisons_user_created_at",
        "saved_comparisons",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_saved_comparisons_user_runs_created_at",
        "saved_comparisons",
        ["user_id", "run_a_id", "run_b_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "saved_stakeholder_reports",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("scenario_profile", sa.Text(), nullable=True),
        sa.Column("horizon_months", sa.Integer(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=True),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("dossier_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("assumptions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "source_type IN ('decision_report', 'compare_result', 'saved_run')",
            name="ck_saved_stakeholder_reports_source_type",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_saved_stakeholder_reports_user_created_at",
        "saved_stakeholder_reports",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_saved_stakeholder_reports_user_source_created_at",
        "saved_stakeholder_reports",
        ["user_id", "source_type", "source_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_saved_stakeholder_reports_user_source_created_at", table_name="saved_stakeholder_reports")
    op.drop_index("idx_saved_stakeholder_reports_user_created_at", table_name="saved_stakeholder_reports")
    op.drop_table("saved_stakeholder_reports")

    op.drop_index("idx_saved_comparisons_user_runs_created_at", table_name="saved_comparisons")
    op.drop_index("idx_saved_comparisons_user_created_at", table_name="saved_comparisons")
    op.drop_table("saved_comparisons")

    op.drop_index("idx_saved_rank_reports_user_run_ids_key_created_at", table_name="saved_rank_reports")
    op.drop_index("idx_saved_rank_reports_user_created_at", table_name="saved_rank_reports")
    op.drop_table("saved_rank_reports")

    op.drop_index("idx_saved_results_user_id_id", table_name="saved_results")
    op.drop_index("idx_saved_results_user_created_at", table_name="saved_results")
    op.drop_table("saved_results")

    op.drop_table("user_usage")
