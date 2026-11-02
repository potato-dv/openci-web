"""Persist agent requests to revisit returned investigations.

Revision ID: 0012_agent_revisit_requests
Revises: 0011_recurring_agent_schedules
"""
from alembic import op
import sqlalchemy as sa


revision = "0012_agent_revisit_requests"
down_revision = "0011_recurring_agent_schedules"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_revisit_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("investigation_id", sa.Integer(), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("investigation_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_work_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="waiting_for_shift"),
        sa.Column("planning_run_id", sa.Integer(), sa.ForeignKey("planning_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("report_id", name="uq_agent_revisit_requests_report"),
        sa.CheckConstraint(
            "status IN ('waiting_for_shift', 'queued', 'routed', 'completed', 'cancelled')",
            name="ck_agent_revisit_requests_status",
        ),
    )
    op.create_index("ix_agent_revisit_requests_investigation_id", "agent_revisit_requests", ["investigation_id"])
    op.create_index("ix_agent_revisit_requests_report_id", "agent_revisit_requests", ["report_id"])
    op.create_index(
        "ix_agent_revisit_requests_agent_status_date",
        "agent_revisit_requests",
        ["agent_id", "status", "target_work_date"],
    )


def downgrade():
    op.drop_index("ix_agent_revisit_requests_agent_status_date", table_name="agent_revisit_requests")
    op.drop_index("ix_agent_revisit_requests_report_id", table_name="agent_revisit_requests")
    op.drop_index("ix_agent_revisit_requests_investigation_id", table_name="agent_revisit_requests")
    op.drop_table("agent_revisit_requests")
