"""Add indexes for paginated activity-log queries.

Revision ID: 0020_activity_log_query_indexes
Revises: 0019_unified_history
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0020_activity_log_query_indexes"
down_revision: Union[str, Sequence[str], None] = "0019_unified_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_activity_logs_object_type",
        "activity_logs",
        ["object_type"],
    )
    op.create_index(
        "ix_activity_logs_action_created_at",
        "activity_logs",
        ["action", "created_at"],
    )
    op.create_index(
        "ix_activity_logs_actor_id_created_at",
        "activity_logs",
        ["actor_id", "created_at"],
    )
    op.create_index(
        "ix_activity_logs_object_lookup",
        "activity_logs",
        ["object_type", "object_id", "created_at"],
    )


def downgrade() -> None:
    for name in (
        "ix_activity_logs_object_lookup",
        "ix_activity_logs_actor_id_created_at",
        "ix_activity_logs_action_created_at",
        "ix_activity_logs_object_type",
    ):
        op.drop_index(name, table_name="activity_logs")
