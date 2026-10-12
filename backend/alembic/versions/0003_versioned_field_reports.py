"""Add structured findings and immutable report revisions.

Revision ID: 0003_versioned_field_reports
Revises: 0002_system_integrity_addresses
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_versioned_field_reports"
down_revision: Union[str, Sequence[str], None] = "0002_system_integrity_addresses"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {item["name"] for item in inspector.get_columns("investigation_reports")}
    indexes = {item["name"] for item in inspector.get_indexes("investigation_reports")}
    checks = {item.get("name") for item in inspector.get_check_constraints("investigation_reports")}

    # Existing reports become revision 1 without changing their content or review links.
    if "version" not in columns:
        op.add_column(
            "investigation_reports",
            sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        )
        op.alter_column("investigation_reports", "version", server_default=None)

    for name, column_type in (
        ("visit_outcome", sa.String(30)),
        ("outcome", sa.String(30)),
        ("verified_address", sa.String(500)),
        ("occupancy_status", sa.String(30)),
        ("property_condition", sa.Text()),
        ("interaction_notes", sa.Text()),
        ("visited_at", sa.DateTime(timezone=True)),
    ):
        if name not in columns:
            op.add_column("investigation_reports", sa.Column(name, column_type, nullable=True))

    if "ck_investigation_reports_status" in checks:
        op.drop_constraint("ck_investigation_reports_status", "investigation_reports", type_="check")
    op.create_check_constraint(
        "ck_investigation_reports_status",
        "investigation_reports",
        "status IN ('draft', 'submitted', 'approved', 'returned_for_correction')",
    )
    op.create_check_constraint(
        "ck_investigation_reports_version_positive",
        "investigation_reports",
        "version > 0",
    )
    op.create_check_constraint(
        "ck_investigation_reports_visit_outcome",
        "investigation_reports",
        "visit_outcome IS NULL OR visit_outcome IN ('visited', 'no_access', 'unable_to_locate')",
    )
    op.create_check_constraint(
        "ck_investigation_reports_outcome",
        "investigation_reports",
        "outcome IS NULL OR outcome IN ('verified', 'not_verified', 'unable_to_verify', 'inconclusive')",
    )
    op.create_check_constraint(
        "ck_investigation_reports_occupancy_status",
        "investigation_reports",
        "occupancy_status IS NULL OR occupancy_status IN ('occupied', 'vacant', 'unknown', 'not_applicable')",
    )

    # Replace the old unique investigation index with a normal lookup index and
    # constrain uniqueness to one report per revision.
    if "ix_investigation_reports_investigation_id" in indexes:
        op.drop_index("ix_investigation_reports_investigation_id", table_name="investigation_reports")
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("investigation_reports")}
    if "ix_investigation_reports_investigation_id" not in indexes:
        op.create_index(
            "ix_investigation_reports_investigation_id",
            "investigation_reports",
            ["investigation_id"],
        )
    uniques = {item.get("name") for item in sa.inspect(bind).get_unique_constraints("investigation_reports")}
    if "uq_investigation_reports_investigation_version" not in uniques:
        op.create_unique_constraint(
            "uq_investigation_reports_investigation_version",
            "investigation_reports",
            ["investigation_id", "version"],
        )
    op.alter_column("investigation_reports", "status", existing_type=sa.String(length=20), type_=sa.String(length=30))


def downgrade() -> None:
    bind = op.get_bind()
    lossy_rows = bind.execute(sa.text("""
        SELECT count(*) FROM investigation_reports
        WHERE version > 1
           OR status IN ('approved', 'returned_for_correction')
           OR visit_outcome IS NOT NULL
           OR outcome IS NOT NULL
           OR verified_address IS NOT NULL
           OR occupancy_status IS NOT NULL
           OR property_condition IS NOT NULL
           OR interaction_notes IS NOT NULL
           OR visited_at IS NOT NULL
    """)).scalar_one()
    if lossy_rows:
        raise RuntimeError("Cannot downgrade: report revisions or structured report data would be lost")

    op.drop_constraint("uq_investigation_reports_investigation_version", "investigation_reports", type_="unique")
    for name in (
        "ck_investigation_reports_version_positive",
        "ck_investigation_reports_visit_outcome",
        "ck_investigation_reports_outcome",
        "ck_investigation_reports_occupancy_status",
        "ck_investigation_reports_status",
    ):
        op.drop_constraint(name, "investigation_reports", type_="check")
    op.drop_index("ix_investigation_reports_investigation_id", table_name="investigation_reports")
    op.create_index(
        "ix_investigation_reports_investigation_id",
        "investigation_reports",
        ["investigation_id"],
        unique=True,
    )
    for name in (
        "visited_at",
        "interaction_notes",
        "property_condition",
        "occupancy_status",
        "verified_address",
        "outcome",
        "visit_outcome",
        "version",
    ):
        op.drop_column("investigation_reports", name)
    op.create_check_constraint(
        "ck_investigation_reports_status",
        "investigation_reports",
        "status IN ('draft', 'submitted')",
    )
    op.alter_column("investigation_reports", "status", existing_type=sa.String(length=30), type_=sa.String(length=20))
