"""Allow the longest review decision value.

Revision ID: 0005_review_decision_len
Revises: 0004_structured_names
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_review_decision_len"
down_revision: Union[str, Sequence[str], None] = "0004_structured_names"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "investigation_reviews",
        "decision",
        existing_type=sa.String(length=20),
        type_=sa.String(length=32),
        existing_nullable=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    has_long_decisions = bind.execute(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM investigation_reviews WHERE length(decision) > 20"
            ")"
        )
    ).scalar_one()
    if has_long_decisions:
        raise RuntimeError(
            "Cannot downgrade review decision length while long decisions exist"
        )

    op.alter_column(
        "investigation_reviews",
        "decision",
        existing_type=sa.String(length=32),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
