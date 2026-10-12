"""Add structured investigation addresses, workflow constraints, and activity logs.

Revision ID: 0002_system_integrity_addresses
Revises: 0001_add_user_is_active
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_system_integrity_addresses"
down_revision: Union[str, Sequence[str], None] = "0001_add_user_is_active"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _constraint_names(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {item.get("name") for item in inspector.get_check_constraints(table)}


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    if "address" in _columns("investigations") and "legacy_address" not in _columns("investigations"):
        op.alter_column("investigations", "address", new_column_name="legacy_address", existing_type=sa.String(500), nullable=True)

    fields = {
        "legacy_address": sa.String(500),
        "house_number": sa.String(100),
        "unit_floor_building_name": sa.String(150),
        "street": sa.String(200),
        "subdivision_village_purok": sa.String(200),
        "region_code": sa.String(10),
        "province_code": sa.String(10),
        "city_municipality_code": sa.String(10),
        "barangay_code": sa.String(10),
        "postal_code": sa.String(10),
        "deleted_at": sa.DateTime(timezone=True),
    }
    existing = _columns("investigations")
    for name, kind in fields.items():
        if name not in existing:
            op.add_column("investigations", sa.Column(name, kind, nullable=True))

    timezone_columns = {
        "investigations": ("created_at", "deleted_at"),
        "investigation_assignments": ("assigned_at", "unassigned_at"),
        "investigation_reports": ("created_at", "updated_at", "submitted_at"),
        "investigation_reviews": ("reviewed_at",),
        "activity_logs": ("created_at",),
    }
    for table, names in timezone_columns.items():
        if table not in tables:
            continue
        for column in sa.inspect(bind).get_columns(table):
            if column["name"] in names and not getattr(column["type"], "timezone", False):
                op.alter_column(
                    table, column["name"], existing_type=column["type"],
                    type_=sa.DateTime(timezone=True),
                    postgresql_using=f"{column['name']} AT TIME ZONE 'UTC'",
                )

    for name in ("region_code", "province_code", "city_municipality_code", "barangay_code", "deleted_at"):
        if name not in {index["name"] for index in sa.inspect(bind).get_indexes("investigations")}:
            op.create_index(f"ix_investigations_{name}", "investigations", [name])

    # Keep the most recently assigned active row when repairing pre-existing duplicates.
    if "investigation_assignments" in tables:
        op.execute(sa.text("""
            WITH ranked AS (
                SELECT id, row_number() OVER (
                    PARTITION BY investigation_id ORDER BY assigned_at DESC, id DESC
                ) AS position
                FROM investigation_assignments WHERE is_active IS TRUE
            )
            UPDATE investigation_assignments AS assignment
            SET is_active = FALSE, unassigned_at = CURRENT_TIMESTAMP
            FROM ranked WHERE ranked.id = assignment.id AND ranked.position > 1
        """))
        op.execute(sa.text("""
            UPDATE investigations AS investigation
            SET assigned_agent_id = assignment.agent_id
            FROM investigation_assignments AS assignment
            WHERE assignment.investigation_id = investigation.id
              AND assignment.is_active IS TRUE
        """))
        indexes = {index["name"] for index in sa.inspect(bind).get_indexes("investigation_assignments")}
        if "uq_assignment_active_per_investigation" not in indexes:
            op.create_index(
                "uq_assignment_active_per_investigation",
                "investigation_assignments",
                ["investigation_id"],
                unique=True,
                postgresql_where=sa.text("is_active IS TRUE"),
            )

    # The legacy UI used `processing` for the current in-progress state.
    op.execute(sa.text("UPDATE investigations SET status = 'in_progress' WHERE status = 'processing'"))

    check_specs = {
        "users": ("ck_users_role", "role IN ('admin', 'supervisor', 'agent')"),
        "investigations": (
            ("ck_investigations_status", "status IN ('pending', 'assigned', 'in_progress', 'under_review', 'returned_for_correction', 'completed')"),
            ("ck_investigations_priority", "priority IN ('normal', 'high', 'urgent')"),
        ),
        "investigation_reports": ("ck_investigation_reports_status", "status IN ('draft', 'submitted')"),
        "investigation_reviews": ("ck_investigation_reviews_decision", "decision IN ('approved', 'returned_for_correction')"),
    }
    report_uniques = {item.get("name") for item in sa.inspect(bind).get_unique_constraints("investigation_reports")}
    if "uq_report_id_investigation" not in report_uniques:
        op.create_unique_constraint("uq_report_id_investigation", "investigation_reports", ["id", "investigation_id"])
    review_fks = {item.get("name") for item in sa.inspect(bind).get_foreign_keys("investigation_reviews")}
    if "fk_reviews_report_investigation" not in review_fks:
        op.execute(sa.text("""
            UPDATE investigation_reviews AS review
            SET investigation_id = report.investigation_id
            FROM investigation_reports AS report
            WHERE review.report_id = report.id
              AND review.investigation_id <> report.investigation_id
        """))
        op.create_foreign_key(
            "fk_reviews_report_investigation", "investigation_reviews", "investigation_reports",
            ["report_id", "investigation_id"], ["id", "investigation_id"], ondelete="CASCADE",
        )
    for table, specs in check_specs.items():
        if table not in tables:
            continue
        if isinstance(specs[0], str):
            specs = (specs,)
        names = _constraint_names(table)
        for name, expression in specs:
            if name not in names:
                op.create_check_constraint(name, table, expression)

    if "activity_logs" not in tables:
        op.create_table(
            "activity_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("action", sa.String(80), nullable=False),
            sa.Column("object_type", sa.String(80), nullable=False),
            sa.Column("object_id", sa.Integer(), nullable=True),
            sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    activity_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("activity_logs")}
    for name, column in (("ix_activity_logs_actor_id", "actor_id"), ("ix_activity_logs_action", "action"), ("ix_activity_logs_object_id", "object_id"), ("ix_activity_logs_created_at", "created_at")):
        if name not in activity_indexes:
            op.create_index(name, "activity_logs", [column])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT count(*) FROM investigations WHERE deleted_at IS NOT NULL")).scalar_one():
        raise RuntimeError("Cannot downgrade while archived investigations exist; restore them first")
    op.drop_constraint("fk_reviews_report_investigation", "investigation_reviews", type_="foreignkey")
    op.drop_constraint("uq_report_id_investigation", "investigation_reports", type_="unique")
    op.drop_index("uq_assignment_active_per_investigation", table_name="investigation_assignments")
    for table, names in {
        "users": ("ck_users_role",),
        "investigations": ("ck_investigations_status", "ck_investigations_priority"),
        "investigation_reports": ("ck_investigation_reports_status",),
        "investigation_reviews": ("ck_investigation_reviews_decision",),
    }.items():
        for name in names:
            op.drop_constraint(name, table, type_="check")
    for table, names in {
        "investigations": ("created_at", "deleted_at"),
        "investigation_assignments": ("assigned_at", "unassigned_at"),
        "investigation_reports": ("created_at", "updated_at", "submitted_at"),
        "investigation_reviews": ("reviewed_at",),
        "activity_logs": ("created_at",),
    }.items():
        for column in names:
            op.alter_column(
                table, column, existing_type=sa.DateTime(timezone=True),
                type_=sa.DateTime(timezone=False),
                postgresql_using=f"{column} AT TIME ZONE 'UTC'",
            )
    # Keep the structured columns and logs for data safety while restoring the old API column.
    op.execute(sa.text("""
        UPDATE investigations SET legacy_address = CONCAT_WS(', ',
            NULLIF(legacy_address, ''), house_number, unit_floor_building_name, street,
            subdivision_village_purok, barangay_code, city_municipality_code,
            province_code, region_code, postal_code
        ) WHERE legacy_address IS NULL
    """))
    op.alter_column("investigations", "legacy_address", new_column_name="address", existing_type=sa.String(500), nullable=False)
