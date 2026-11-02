"""Recurring agent availability, shift breaks, and durable planning triggers.

Revision ID: 0011_recurring_agent_schedules
Revises: 0010_automatic_assignment_source
"""
from alembic import op
import sqlalchemy as sa


revision = "0011_recurring_agent_schedules"
down_revision = "0010_automatic_assignment_source"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_work_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("depot_latitude", sa.Float(), nullable=True),
        sa.Column("depot_longitude", sa.Float(), nullable=True),
        sa.Column("depot_label", sa.String(500), nullable=True),
        sa.Column("depot_source", sa.String(20), nullable=True),
        sa.Column("depot_provider_ref", sa.String(100), nullable=True),
        sa.Column("end_latitude", sa.Float(), nullable=True),
        sa.Column("end_longitude", sa.Float(), nullable=True),
        sa.Column("end_label", sa.String(500), nullable=True),
        sa.Column("end_source", sa.String(20), nullable=True),
        sa.Column("end_provider_ref", sa.String(100), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("agent_id", name="uq_agent_work_profiles_agent"),
        sa.CheckConstraint("(depot_latitude IS NULL AND depot_longitude IS NULL) OR (depot_latitude BETWEEN -90 AND 90 AND depot_longitude BETWEEN -180 AND 180)", name="ck_agent_work_profiles_depot_coordinates"),
        sa.CheckConstraint("(end_latitude IS NULL AND end_longitude IS NULL) OR (end_latitude IS NOT NULL AND end_longitude IS NOT NULL AND end_latitude BETWEEN -90 AND 90 AND end_longitude BETWEEN -180 AND 180)", name="ck_agent_work_profiles_end_coordinates"),
    )
    op.create_index("ix_agent_work_profiles_agent_id", "agent_work_profiles", ["agent_id"])

    op.create_table(
        "agent_weekly_schedules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_until", sa.Date(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("region_code", sa.String(10), nullable=False),
        sa.Column("max_visits", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("max_open_cases", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("days", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("agent_id", "effective_from", name="uq_agent_weekly_schedules_agent_start"),
        sa.CheckConstraint("effective_until IS NULL OR effective_until >= effective_from", name="ck_agent_weekly_schedules_effective_range"),
        sa.CheckConstraint("max_visits > 0", name="ck_agent_weekly_schedules_max_visits_positive"),
        sa.CheckConstraint("max_open_cases > 0", name="ck_agent_weekly_schedules_max_open_cases_positive"),
    )
    op.create_index("ix_agent_weekly_schedules_agent_effective", "agent_weekly_schedules", ["agent_id", "effective_from", "effective_until"])

    op.create_table(
        "planning_triggers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("region_code", sa.String(10), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="'pending'"),
        sa.Column("last_error", sa.String(120), nullable=True),
        sa.Column("input_fingerprint", sa.String(64), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("work_date", "region_code", name="uq_planning_triggers_scope"),
        sa.CheckConstraint("status IN ('pending', 'processing', 'retry', 'complete', 'failed')", name="ck_planning_triggers_status"),
    )
    op.create_index("ix_planning_triggers_dispatch", "planning_triggers", ["status", "next_attempt_at", "work_date"])

    op.add_column("agent_shifts", sa.Column("source", sa.String(20), nullable=False, server_default="manual"))
    op.add_column("agent_shifts", sa.Column("schedule_version_id", sa.Integer(), sa.ForeignKey("agent_weekly_schedules.id", ondelete="SET NULL"), nullable=True))
    op.add_column("agent_shifts", sa.Column("break_starts_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_shifts", sa.Column("break_ends_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_shifts", sa.Column("last_completed_investigation_id", sa.Integer(), sa.ForeignKey("investigations.id", ondelete="SET NULL"), nullable=True))
    op.add_column("agent_shifts", sa.Column("last_completed_report_id", sa.Integer(), sa.ForeignKey("investigation_reports.id", ondelete="SET NULL"), nullable=True))
    op.add_column("agent_shifts", sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_shifts", sa.Column("last_completed_latitude", sa.Float(), nullable=True))
    op.add_column("agent_shifts", sa.Column("last_completed_longitude", sa.Float(), nullable=True))
    op.create_check_constraint("ck_agent_shifts_source", "agent_shifts", "source IN ('manual', 'recurring')")
    op.create_check_constraint("ck_agent_shifts_break_interval", "agent_shifts", "(break_starts_at IS NULL AND break_ends_at IS NULL) OR (break_starts_at IS NOT NULL AND break_ends_at IS NOT NULL AND break_ends_at > break_starts_at AND break_starts_at >= shift_starts_at AND break_ends_at <= shift_ends_at)")
    op.create_check_constraint("ck_agent_shifts_last_stop_coordinates", "agent_shifts", "(last_completed_latitude IS NULL AND last_completed_longitude IS NULL) OR (last_completed_latitude BETWEEN -90 AND 90 AND last_completed_longitude BETWEEN -180 AND 180)")

    op.add_column("planning_items", sa.Column("estimated_service_start_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("planning_items", sa.Column("waiting_seconds", sa.Integer(), nullable=True))
    op.add_column("planning_runs", sa.Column("movable_investigation_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column("planning_routes", sa.Column("total_service_seconds", sa.Integer(), nullable=True))
    op.add_column("planning_routes", sa.Column("total_waiting_seconds", sa.Integer(), nullable=True))
    op.add_column("planning_routes", sa.Column("total_break_seconds", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("planning_routes", "total_break_seconds")
    op.drop_column("planning_routes", "total_waiting_seconds")
    op.drop_column("planning_routes", "total_service_seconds")
    op.drop_column("planning_items", "waiting_seconds")
    op.drop_column("planning_items", "estimated_service_start_at")
    op.drop_column("planning_runs", "movable_investigation_ids")
    op.drop_constraint("ck_agent_shifts_last_stop_coordinates", "agent_shifts", type_="check")
    op.drop_constraint("ck_agent_shifts_break_interval", "agent_shifts", type_="check")
    op.drop_constraint("ck_agent_shifts_source", "agent_shifts", type_="check")
    for name in ("last_completed_longitude", "last_completed_latitude", "last_completed_at", "last_completed_report_id", "last_completed_investigation_id", "break_ends_at", "break_starts_at", "schedule_version_id", "source"):
        op.drop_column("agent_shifts", name)
    op.drop_index("ix_planning_triggers_dispatch", table_name="planning_triggers")
    op.drop_table("planning_triggers")
    op.drop_index("ix_agent_weekly_schedules_agent_effective", table_name="agent_weekly_schedules")
    op.drop_table("agent_weekly_schedules")
    op.drop_index("ix_agent_work_profiles_agent_id", table_name="agent_work_profiles")
    op.drop_table("agent_work_profiles")
