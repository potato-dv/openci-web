"""Add confirmed investigation locations and planning records.

Revision ID: 0007_routing_and_planning
Revises: 0006_report_revision_unique
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_routing_and_planning"
down_revision: Union[str, Sequence[str], None] = "0006_report_revision_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("investigations", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("investigations", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("investigations", sa.Column("location_source", sa.String(length=20), nullable=True))
    op.add_column("investigations", sa.Column("location_provider_ref", sa.String(length=100), nullable=True))
    op.add_column("investigations", sa.Column("location_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("investigations", sa.Column("location_confirmed_by_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_investigations_location_confirmed_by_id_users",
        "investigations", "users", ["location_confirmed_by_id"], ["id"], ondelete="SET NULL",
    )
    for resolution in (7, 8, 9):
        op.add_column("investigations", sa.Column(f"h3_r{resolution}", sa.String(length=15), nullable=True))
        op.create_index(f"ix_investigations_h3_r{resolution}", "investigations", [f"h3_r{resolution}"])
    op.add_column("investigations", sa.Column("service_duration_seconds", sa.Integer(), nullable=False, server_default="2700"))
    op.add_column("investigations", sa.Column("visit_not_before_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("investigations", sa.Column("visit_due_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_investigations_coordinate_pair", "investigations",
        "(latitude IS NULL AND longitude IS NULL) OR "
        "(latitude IS NOT NULL AND longitude IS NOT NULL AND latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)",
    )
    op.create_check_constraint(
        "ck_investigations_location_confirmation", "investigations",
        "(latitude IS NULL AND longitude IS NULL AND location_source IS NULL AND location_confirmed_at IS NULL) OR "
        "(latitude IS NOT NULL AND longitude IS NOT NULL AND location_source IS NOT NULL "
        "AND location_source IN ('nominatim', 'manual') "
        "AND location_confirmed_at IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_investigations_h3_matches_location", "investigations",
        "(latitude IS NULL AND h3_r7 IS NULL AND h3_r8 IS NULL AND h3_r9 IS NULL) OR "
        "(latitude IS NOT NULL AND h3_r7 IS NOT NULL AND h3_r8 IS NOT NULL AND h3_r9 IS NOT NULL)",
    )
    op.create_check_constraint("ck_investigations_service_duration_positive", "investigations", "service_duration_seconds > 0")
    op.create_check_constraint(
        "ck_investigations_visit_window_order", "investigations",
        "visit_not_before_at IS NULL OR visit_due_at IS NULL OR visit_due_at > visit_not_before_at",
    )

    op.create_table(
        "planning_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requested_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("region_code", sa.String(length=10), nullable=False),
        sa.Column("investigation_ids", sa.JSON(), nullable=False),
        sa.Column("agent_ids", sa.JSON(), nullable=False),
        sa.Column("locked_assignments", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("input_digest", sa.String(length=64), nullable=True),
        sa.Column("result_digest", sa.String(length=80), nullable=True),
        sa.Column("osrm_dataset", sa.String(length=100), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('queued', 'running', 'ready', 'failed', 'stale', 'applied')", name="ck_planning_runs_status"),
    )
    op.create_index("ix_planning_runs_requested_by_id", "planning_runs", ["requested_by_id"])
    op.create_index("ix_planning_runs_region_code", "planning_runs", ["region_code"])
    op.create_index("ix_planning_runs_status", "planning_runs", ["status"])
    op.create_index("ix_planning_runs_scope", "planning_runs", ["work_date", "region_code", "status"])

    op.create_table(
        "agent_shifts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("region_code", sa.String(length=10), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("shift_starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shift_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("start_latitude", sa.Float(), nullable=False),
        sa.Column("start_longitude", sa.Float(), nullable=False),
        sa.Column("end_latitude", sa.Float(), nullable=True),
        sa.Column("end_longitude", sa.Float(), nullable=True),
        sa.Column("max_visits", sa.Integer(), nullable=False),
        sa.Column("max_open_cases", sa.Integer(), nullable=False),
        sa.Column("current_planning_run_id", sa.Integer(), sa.ForeignKey("planning_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("agent_id", "work_date", name="uq_agent_shifts_agent_date"),
        sa.CheckConstraint("shift_ends_at > shift_starts_at", name="ck_agent_shifts_time_order"),
        sa.CheckConstraint("max_visits > 0", name="ck_agent_shifts_max_visits_positive"),
        sa.CheckConstraint("max_open_cases > 0", name="ck_agent_shifts_max_open_cases_positive"),
        sa.CheckConstraint("(start_latitude IS NULL AND start_longitude IS NULL) OR (start_latitude BETWEEN -90 AND 90 AND start_longitude BETWEEN -180 AND 180)", name="ck_agent_shifts_start_coordinates"),
        sa.CheckConstraint("(end_latitude IS NULL AND end_longitude IS NULL) OR (end_latitude IS NOT NULL AND end_longitude IS NOT NULL AND end_latitude BETWEEN -90 AND 90 AND end_longitude BETWEEN -180 AND 180)", name="ck_agent_shifts_end_coordinates"),
    )
    op.create_index("ix_agent_shifts_date_region_available", "agent_shifts", ["work_date", "region_code", "is_available"])

    op.create_table(
        "planning_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("planning_run_id", sa.Integer(), sa.ForeignKey("planning_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("investigation_id", sa.Integer(), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=True),
        sa.Column("estimated_arrival_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("travel_seconds", sa.Integer(), nullable=True),
        sa.Column("travel_metres", sa.Integer(), nullable=True),
        sa.Column("prior_assignment_id", sa.Integer(), sa.ForeignKey("investigation_assignments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("applied_assignment_id", sa.Integer(), sa.ForeignKey("investigation_assignments.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("planning_run_id", "investigation_id", name="uq_planning_items_run_investigation"),
        sa.CheckConstraint("outcome IN ('assigned', 'unassigned')", name="ck_planning_items_outcome"),
    )
    op.create_index("ix_planning_items_route", "planning_items", ["planning_run_id", "agent_id", "sequence"])


def downgrade() -> None:
    op.drop_index("ix_planning_items_route", table_name="planning_items")
    op.drop_table("planning_items")
    op.drop_index("ix_agent_shifts_date_region_available", table_name="agent_shifts")
    op.drop_table("agent_shifts")
    op.drop_index("ix_planning_runs_scope", table_name="planning_runs")
    op.drop_index("ix_planning_runs_status", table_name="planning_runs")
    op.drop_index("ix_planning_runs_region_code", table_name="planning_runs")
    op.drop_index("ix_planning_runs_requested_by_id", table_name="planning_runs")
    op.drop_table("planning_runs")
    op.drop_constraint("ck_investigations_visit_window_order", "investigations", type_="check")
    op.drop_constraint("ck_investigations_service_duration_positive", "investigations", type_="check")
    op.drop_constraint("ck_investigations_h3_matches_location", "investigations", type_="check")
    op.drop_constraint("ck_investigations_location_confirmation", "investigations", type_="check")
    op.drop_constraint("ck_investigations_coordinate_pair", "investigations", type_="check")
    op.drop_column("investigations", "visit_due_at")
    op.drop_column("investigations", "visit_not_before_at")
    op.drop_column("investigations", "service_duration_seconds")
    for resolution in (7, 8, 9):
        op.drop_index(f"ix_investigations_h3_r{resolution}", table_name="investigations")
        op.drop_column("investigations", f"h3_r{resolution}")
    op.drop_constraint("fk_investigations_location_confirmed_by_id_users", "investigations", type_="foreignkey")
    op.drop_column("investigations", "location_confirmed_by_id")
    op.drop_column("investigations", "location_confirmed_at")
    op.drop_column("investigations", "location_provider_ref")
    op.drop_column("investigations", "location_source")
    op.drop_column("investigations", "longitude")
    op.drop_column("investigations", "latitude")
