"""Add transactional outbox for real-time notifications.

Revision ID: 0021_realtime_outbox
Revises: 0020_activity_log_query_indexes
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0021_realtime_outbox"
down_revision: Union[str, Sequence[str], None] = "0020_activity_log_query_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "realtime_outbox_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Uuid(as_uuid=True), nullable=False, unique=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.String(length=80), nullable=False),
        sa.Column("investigation_id", sa.Integer(), nullable=True),
        sa.Column("recipient_user_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("recipient_roles", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=80), nullable=True),
    )
    op.create_index(
        "ix_realtime_outbox_pending",
        "realtime_outbox_events",
        ["published_at", "available_at", "id"],
    )
    op.create_index(
        "ix_realtime_outbox_events_investigation_id",
        "realtime_outbox_events",
        ["investigation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_realtime_outbox_events_investigation_id", table_name="realtime_outbox_events")
    op.drop_index("ix_realtime_outbox_pending", table_name="realtime_outbox_events")
    op.drop_table("realtime_outbox_events")
