"""Allow multiple report revisions per investigation.

Revision ID: 0006_report_revision_unique
Revises: 0005_review_decision_len
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_report_revision_unique"
down_revision: Union[str, Sequence[str], None] = "0005_review_decision_len"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    unique_constraints = sa.inspect(op.get_bind()).get_unique_constraints(
        "investigation_reports"
    )
    for constraint in unique_constraints:
        if constraint.get("column_names") == ["investigation_id"]:
            op.drop_constraint(
                constraint["name"],
                "investigation_reports",
                type_="unique",
            )


def downgrade() -> None:
    bind = op.get_bind()
    has_multiple_versions = bind.execute(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM investigation_reports "
            "GROUP BY investigation_id HAVING count(*) > 1"
            ")"
        )
    ).scalar_one()
    if has_multiple_versions:
        raise RuntimeError(
            "Cannot downgrade report revisions while investigations have multiple versions"
        )

    op.create_unique_constraint(
        "uq_investigation_reports_investigation_id",
        "investigation_reports",
        ["investigation_id"],
    )
