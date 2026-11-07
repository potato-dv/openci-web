"""Add per-Agent feature overrides.

Revision ID: 0018_agent_feature_permissions
Revises: 0017_manual_assignment_hold
"""
from alembic import op
import sqlalchemy as sa


revision = "0018_agent_feature_permissions"
down_revision = "0017_manual_assignment_hold"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_permission_overrides",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("feature_code", sa.String(length=100), nullable=False),
        sa.Column("effect", sa.String(length=10), nullable=False),
        sa.CheckConstraint("effect IN ('allow', 'deny')", name="ck_user_permission_override_effect"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "feature_code", name="uq_user_permission_override_feature"),
    )
    op.create_index(
        "ix_user_permission_overrides_user_id",
        "user_permission_overrides",
        ["user_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_user_permission_overrides_user_id", table_name="user_permission_overrides")
    op.drop_table("user_permission_overrides")
