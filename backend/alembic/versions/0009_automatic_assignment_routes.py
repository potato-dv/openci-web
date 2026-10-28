"""Track automatic route refreshes from direct assignments.

Revision ID: 0009_automatic_assignment_routes
Revises: 0008_planning_route_geometry
"""
from alembic import op
import sqlalchemy as sa


revision = "0009_automatic_assignment_routes"
down_revision = "0008_planning_route_geometry"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "planning_runs",
        sa.Column(
            "auto_publish",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "planning_runs",
        sa.Column(
            "auto_assignment_id",
            sa.Integer(),
            sa.ForeignKey("investigation_assignments.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_planning_runs_auto_assignment_id",
        "planning_runs",
        ["auto_assignment_id"],
    )
    op.add_column(
        "investigation_assignments",
        sa.Column("auto_route_status", sa.String(length=24), nullable=True),
    )
    op.add_column(
        "investigation_assignments",
        sa.Column("auto_route_work_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "investigation_assignments",
        sa.Column("auto_route_agent_ids", sa.JSON(), nullable=True),
    )
    op.add_column(
        "investigation_assignments",
        sa.Column("auto_route_run_ids", sa.JSON(), nullable=True),
    )
    op.add_column(
        "investigation_assignments",
        sa.Column("auto_route_errors", sa.JSON(), nullable=True),
    )


def downgrade():
    op.drop_column("investigation_assignments", "auto_route_errors")
    op.drop_column("investigation_assignments", "auto_route_run_ids")
    op.drop_column("investigation_assignments", "auto_route_agent_ids")
    op.drop_column("investigation_assignments", "auto_route_work_date")
    op.drop_column("investigation_assignments", "auto_route_status")
    op.drop_index("ix_planning_runs_auto_assignment_id", table_name="planning_runs")
    op.drop_column("planning_runs", "auto_assignment_id")
    op.drop_column("planning_runs", "auto_publish")
