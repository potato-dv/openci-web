"""Keep manually unassigned investigations out of automatic assignment.

Revision ID: 0017_manual_assignment_hold
Revises: 0016_route_events
"""
from alembic import op
import sqlalchemy as sa


revision = "0017_manual_assignment_hold"
down_revision = "0016_route_events"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "investigations",
        sa.Column(
            "manual_assignment_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column("investigations", "manual_assignment_required")
