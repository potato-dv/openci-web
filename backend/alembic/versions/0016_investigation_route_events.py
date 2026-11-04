"""Track field attempts, no-contact deferrals, and shift carry-overs.

Revision ID: 0016_route_events
Revises: 0015_vroom_route_timing
"""
from alembic import op
import sqlalchemy as sa


revision = "0016_route_events"
down_revision = "0015_vroom_route_timing"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agent_shifts", sa.Column("last_attempted_investigation_id", sa.Integer(), sa.ForeignKey("investigations.id", ondelete="SET NULL"), nullable=True))
    op.add_column("agent_shifts", sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_shifts", sa.Column("last_attempted_latitude", sa.Float(), nullable=True))
    op.add_column("agent_shifts", sa.Column("last_attempted_longitude", sa.Float(), nullable=True))
    op.create_table(
        "investigation_route_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("investigation_id", sa.Integer(), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("planning_run_id", sa.Integer(), sa.ForeignKey("planning_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("parent_event_id", sa.Integer(), sa.ForeignKey("investigation_route_events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("retry_number", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reason", sa.String(length=80), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("contact_available_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contact_available_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("next_work_date", sa.Date(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("event_type IN ('no_contact', 'shift_end_not_visited')", name="ck_route_events_type"),
        sa.CheckConstraint("state IN ('deferred', 'retrying', 'retry_failed', 'carried_over', 'resolved')", name="ck_route_events_state"),
        sa.CheckConstraint("retry_number IN (0, 1)", name="ck_route_events_retry_number"),
        sa.CheckConstraint(
            "(contact_available_from IS NULL AND contact_available_until IS NULL) OR "
            "(contact_available_until IS NULL OR contact_available_from IS NULL OR contact_available_until > contact_available_from)",
            name="ck_route_events_contact_window",
        ),
        sa.UniqueConstraint("investigation_id", "agent_id", "work_date", "retry_number", name="uq_route_event_investigation_agent_date_retry"),
    )
    op.create_index("ix_investigation_route_events_investigation_id", "investigation_route_events", ["investigation_id"])
    op.create_index("ix_investigation_route_events_agent_id", "investigation_route_events", ["agent_id"])
    op.create_index("ix_route_events_agent_date_state", "investigation_route_events", ["agent_id", "work_date", "state"])
    op.create_index("ix_route_events_investigation_attempted", "investigation_route_events", ["investigation_id", "attempted_at"])


def downgrade():
    op.drop_index("ix_route_events_investigation_attempted", table_name="investigation_route_events")
    op.drop_index("ix_route_events_agent_date_state", table_name="investigation_route_events")
    op.drop_index("ix_investigation_route_events_agent_id", table_name="investigation_route_events")
    op.drop_index("ix_investigation_route_events_investigation_id", table_name="investigation_route_events")
    op.drop_table("investigation_route_events")
    op.drop_column("agent_shifts", "last_attempted_longitude")
    op.drop_column("agent_shifts", "last_attempted_latitude")
    op.drop_column("agent_shifts", "last_attempted_at")
    op.drop_column("agent_shifts", "last_attempted_investigation_id")
