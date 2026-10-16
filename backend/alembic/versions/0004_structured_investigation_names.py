"""Store investigation subject names in structured columns.

Revision ID: 0004_structured_names
Revises: 0003_versioned_field_reports
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_structured_names"
down_revision: Union[str, Sequence[str], None] = "0003_versioned_field_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NAME_CONSTRAINT = "ck_investigations_structured_subject_name"


def upgrade() -> None:
    # Existing names are intentionally retained intact. Whitespace alone cannot
    # establish which words are first, middle, or last names.
    with op.batch_alter_table("investigations") as batch_op:
        batch_op.alter_column(
            "subject_name",
            new_column_name="legacy_subject_name",
            existing_type=sa.String(length=255),
            existing_nullable=False,
            nullable=True,
        )
        batch_op.add_column(sa.Column("first_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("middle_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("last_name", sa.String(length=255), nullable=True))
        batch_op.create_check_constraint(
            NAME_CONSTRAINT,
            "(legacy_subject_name IS NOT NULL AND first_name IS NULL AND middle_name IS NULL AND last_name IS NULL) "
            "OR (legacy_subject_name IS NULL "
            "AND first_name IS NOT NULL AND length(trim(first_name)) > 0 "
            "AND last_name IS NOT NULL AND length(trim(last_name)) > 0 "
            "AND (middle_name IS NULL OR length(trim(middle_name)) > 0) "
            "AND length(trim(first_name)) + length(trim(last_name)) "
            "+ coalesce(length(trim(middle_name)), 0) "
            "+ CASE WHEN middle_name IS NULL THEN 1 ELSE 2 END <= 255)",
        )


def downgrade() -> None:
    op.add_column(
        "investigations",
        sa.Column("subject_name", sa.String(length=255), nullable=True),
    )
    op.get_bind().execute(
        sa.text(
            "UPDATE investigations SET subject_name = CASE "
            "WHEN legacy_subject_name IS NOT NULL THEN legacy_subject_name "
            "ELSE trim(first_name) "
            "|| CASE WHEN middle_name IS NOT NULL THEN ' ' || trim(middle_name) ELSE '' END "
            "|| ' ' || trim(last_name) END"
        )
    )

    with op.batch_alter_table("investigations") as batch_op:
        batch_op.drop_constraint(NAME_CONSTRAINT, type_="check")
        batch_op.alter_column(
            "subject_name",
            existing_type=sa.String(length=255),
            nullable=False,
        )
        batch_op.drop_column("first_name")
        batch_op.drop_column("middle_name")
        batch_op.drop_column("last_name")
        batch_op.drop_column("legacy_subject_name")
