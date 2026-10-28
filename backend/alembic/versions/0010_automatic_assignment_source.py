"""Record automatic assignment provenance and coalesced planning triggers.

Revision ID: 0010_automatic_assignment_source
Revises: 0009_automatic_assignment_routes
"""
from alembic import op
import sqlalchemy as sa


revision = "0010_automatic_assignment_source"
down_revision = "0009_automatic_assignment_routes"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "investigation_assignments",
        sa.Column("assignment_source", sa.String(length=20), nullable=False, server_default="manual"),
    )
    op.create_check_constraint(
        "ck_investigation_assignments_source",
        "investigation_assignments",
        "assignment_source IN ('manual', 'automatic')",
    )
    op.add_column(
        "planning_runs",
        sa.Column(
            "auto_replan_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "planning_runs",
        sa.Column(
            "auto_assignment_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade():
    op.drop_column("planning_runs", "auto_assignment_ids")
    op.drop_column("planning_runs", "auto_replan_requested")
    op.drop_constraint(
        "ck_investigation_assignments_source",
        "investigation_assignments",
        type_="check",
    )
    op.drop_column("investigation_assignments", "assignment_source")
