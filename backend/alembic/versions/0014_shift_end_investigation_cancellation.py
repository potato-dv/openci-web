"""Persist shift-end cancellation and next-day reopening for investigations.

Revision ID: 0014_shift_end_cancel
Revises: 0013_jwt_refresh_sessions
"""
from alembic import op
import sqlalchemy as sa


revision = "0014_shift_end_cancel"
down_revision = "0013_jwt_refresh_sessions"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("investigations") as batch_op:
        batch_op.add_column(sa.Column("reopen_on", sa.Date(), nullable=True))
        batch_op.drop_constraint("ck_investigations_status", type_="check")
        batch_op.create_check_constraint(
            "ck_investigations_status",
            "status IN ('pending', 'assigned', 'in_progress', 'under_review', "
            "'returned_for_correction', 'completed', 'cancelled')",
        )
        batch_op.create_check_constraint(
            "ck_investigations_reopen_on_status",
            "(status = 'cancelled' AND reopen_on IS NOT NULL) OR "
            "(status <> 'cancelled' AND reopen_on IS NULL)",
        )

    op.create_index(
        "ix_investigations_reopen_on_status",
        "investigations",
        ["status", "reopen_on"],
    )


def downgrade():
    op.execute("UPDATE investigations SET status = 'pending', reopen_on = NULL WHERE status = 'cancelled'")
    op.drop_index("ix_investigations_reopen_on_status", table_name="investigations")
    with op.batch_alter_table("investigations") as batch_op:
        batch_op.drop_constraint("ck_investigations_reopen_on_status", type_="check")
        batch_op.drop_constraint("ck_investigations_status", type_="check")
        batch_op.create_check_constraint(
            "ck_investigations_status",
            "status IN ('pending', 'assigned', 'in_progress', 'under_review', "
            "'returned_for_correction', 'completed')",
        )
        batch_op.drop_column("reopen_on")
