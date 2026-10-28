"""Persist road geometry and manual shift location labels.

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_planning_route_geometry"
down_revision = "0007_routing_and_planning"
branch_labels = None
depends_on = None


def upgrade():
    for prefix in ("start", "end"):
        for suffix, size in (("label", 500), ("source", 20), ("provider_ref", 100)):
            op.add_column("agent_shifts", sa.Column(f"{prefix}_location_{suffix}", sa.String(size), nullable=True))
    op.create_table(
        "planning_routes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("planning_run_id", sa.Integer(), sa.ForeignKey("planning_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("geometry_status", sa.String(20), nullable=False),
        sa.Column("geometry_error_code", sa.String(100)),
        sa.Column("geometry", sa.JSON()),
        sa.Column("geometry_digest", sa.String(64)),
        sa.Column("total_distance_metres", sa.Integer()),
        sa.Column("total_travel_seconds", sa.Integer()),
        sa.Column("start", sa.JSON(), nullable=False),
        sa.Column("end", sa.JSON()),
        sa.UniqueConstraint("planning_run_id", "agent_id", name="uq_planning_routes_run_agent"),
        sa.CheckConstraint("geometry_status IN ('ready', 'failed')", name="ck_planning_routes_geometry_status"),
    )
    op.create_index("ix_planning_routes_planning_run_id", "planning_routes", ["planning_run_id"])
    op.create_index("ix_planning_routes_agent_id", "planning_routes", ["agent_id"])


def downgrade():
    op.drop_table("planning_routes")
    for prefix in ("start", "end"):
        for suffix in ("label", "source", "provider_ref"):
            op.drop_column("agent_shifts", f"{prefix}_location_{suffix}")
