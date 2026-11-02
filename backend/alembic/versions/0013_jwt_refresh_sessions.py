"""Add revocable refresh sessions and token rotation history.

Revision ID: 0013_jwt_refresh_sessions
Revises: 0012_agent_revisit_requests
"""
from alembic import op
import sqlalchemy as sa


revision = "0013_jwt_refresh_sessions"
down_revision = "0012_agent_revisit_requests"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_interactive_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(length=32), nullable=True),
        sa.CheckConstraint(
            "revoke_reason IS NULL OR revoke_reason IN ('logout', 'refresh_reuse', 'idle_expired', 'absolute_expired', 'account_changed')",
            name="ck_auth_sessions_revoke_reason",
        ),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index(
        "ix_auth_sessions_expiry_revocation",
        "auth_sessions",
        ["absolute_expires_at", "revoked_at"],
    )

    op.create_table(
        "auth_refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Uuid(as_uuid=True), sa.ForeignKey("auth_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_auth_refresh_tokens_hash"),
        sa.UniqueConstraint("session_id", "generation", name="uq_auth_refresh_tokens_session_generation"),
        sa.CheckConstraint("generation >= 0", name="ck_auth_refresh_tokens_generation_nonnegative"),
    )
    op.create_index("ix_auth_refresh_tokens_session_id", "auth_refresh_tokens", ["session_id"])


def downgrade():
    op.drop_index("ix_auth_refresh_tokens_session_id", table_name="auth_refresh_tokens")
    op.drop_table("auth_refresh_tokens")
    op.drop_index("ix_auth_sessions_expiry_revocation", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
