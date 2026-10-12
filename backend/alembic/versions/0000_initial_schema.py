"""Create the OpenCI schema for new installations.

Revision ID: 0000_initial_schema
Revises:
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0000_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    if "users" not in existing:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("email", sa.String(255), nullable=False, unique=True),
            sa.Column("password", sa.String(255), nullable=False),
            sa.Column("role", sa.String(50), nullable=False, server_default="agent"),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)
    if "investigations" not in existing:
        op.create_table(
            "investigations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("reference_number", sa.String(50), nullable=False, unique=True),
            sa.Column("subject_name", sa.String(255), nullable=False),
            sa.Column("address", sa.String(500), nullable=False),
            sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
            sa.Column("priority", sa.String(50), nullable=False, server_default="normal"),
            sa.Column("assigned_agent_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        for name, column in (
            ("ix_investigations_reference_number", "reference_number"),
            ("ix_investigations_assigned_agent_id", "assigned_agent_id"),
        ):
            op.create_index(name, "investigations", [column], unique=column == "reference_number")
    if "investigation_assignments" not in existing:
        op.create_table(
            "investigation_assignments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("investigation_id", sa.Integer(), sa.ForeignKey("investigations.id"), nullable=False),
            sa.Column("agent_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("assigned_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("note", sa.String(500), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("assigned_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("unassigned_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_investigation_assignments_investigation_id", "investigation_assignments", ["investigation_id"])
        op.create_index("ix_investigation_assignments_agent_id", "investigation_assignments", ["agent_id"])
        op.create_index("ix_investigation_assignments_assigned_by_id", "investigation_assignments", ["assigned_by_id"])
    if "investigation_reports" not in existing:
        op.create_table(
            "investigation_reports",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("investigation_id", sa.Integer(), sa.ForeignKey("investigations.id"), nullable=False, unique=True),
            sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("submitted_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_investigation_reports_investigation_id", "investigation_reports", ["investigation_id"], unique=True)
        op.create_index("ix_investigation_reports_author_id", "investigation_reports", ["author_id"])
    if "investigation_reviews" not in existing:
        op.create_table(
            "investigation_reviews",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("investigation_id", sa.Integer(), sa.ForeignKey("investigations.id"), nullable=False),
            sa.Column("report_id", sa.Integer(), sa.ForeignKey("investigation_reports.id"), nullable=False),
            sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("decision", sa.String(20), nullable=False),
            sa.Column("comments", sa.Text(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        for column in ("investigation_id", "report_id", "reviewer_id"):
            op.create_index(f"ix_investigation_reviews_{column}", "investigation_reviews", [column])
def downgrade() -> None:
    for table in ("investigation_reviews", "investigation_reports", "investigation_assignments", "investigations", "users"):
        op.drop_table(table)
