"""Persist VROOM planned departure and arrival times.

Revision ID: 0015_vroom_route_timing
Revises: 0014_shift_end_cancel
"""
from alembic import op
import sqlalchemy as sa


revision = "0015_vroom_route_timing"
down_revision = "0014_shift_end_cancel"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "planning_items",
        sa.Column("planned_arrival_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "planning_routes",
        sa.Column("planned_departure_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("planning_routes", "planned_departure_at")
    op.drop_column("planning_items", "planned_arrival_at")
