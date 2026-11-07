"""Consolidate Agent investigation history permissions.

Revision ID: 0019_unified_history
Revises: 0018_agent_feature_permissions
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0019_unified_history"
down_revision: Union[str, Sequence[str], None] = "0018_agent_feature_permissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


HISTORY_FEATURE = "investigation.view_own_history"
LEGACY_DEFAULTS = {
    "investigation.view_own_report_history": True,
    "investigation.view_own_activity": False,
    "investigation.view_own_completed": True,
}


def upgrade() -> None:
    bind = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("role", sa.String),
    )
    overrides = sa.table(
        "user_permission_overrides",
        sa.column("id", sa.Integer),
        sa.column("user_id", sa.Integer),
        sa.column("feature_code", sa.String),
        sa.column("effect", sa.String),
    )

    agent_ids = bind.execute(
        sa.select(users.c.id).where(users.c.role == "agent")
    ).scalars().all()
    relevant_codes = (*LEGACY_DEFAULTS, HISTORY_FEATURE)
    rows = bind.execute(
        sa.select(overrides.c.user_id, overrides.c.feature_code, overrides.c.effect)
        .where(overrides.c.feature_code.in_(relevant_codes))
    ).all()
    by_user: dict[int, dict[str, str]] = {}
    for user_id, feature_code, effect in rows:
        by_user.setdefault(user_id, {})[feature_code] = effect

    inserts: list[dict[str, object]] = []
    updates: list[tuple[int, str]] = []
    for agent_id in agent_ids:
        current = by_user.get(agent_id, {})
        legacy_effective = {
            code: current.get(code, "allow" if default_allowed else "deny") == "allow"
            for code, default_allowed in LEGACY_DEFAULTS.items()
        }

        # A single Allow exposes all three history areas. Only grant it when
        # every legacy effective permission allowed access; any prior/default
        # restriction therefore wins during consolidation.
        allowed = all(legacy_effective.values())
        if current.get(HISTORY_FEATURE) == "deny":
            allowed = False
        effect = "allow" if allowed else "deny"

        if HISTORY_FEATURE in current:
            updates.append((agent_id, effect))
        else:
            inserts.append({"user_id": agent_id, "feature_code": HISTORY_FEATURE, "effect": effect})

    for agent_id, effect in updates:
        bind.execute(
            sa.update(overrides)
            .where(overrides.c.user_id == agent_id)
            .where(overrides.c.feature_code == HISTORY_FEATURE)
            .values(effect=effect)
        )
    if inserts:
        bind.execute(sa.insert(overrides), inserts)

    bind.execute(
        sa.delete(overrides).where(overrides.c.feature_code.in_(tuple(LEGACY_DEFAULTS)))
    )


def downgrade() -> None:
    bind = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("role", sa.String),
    )
    overrides = sa.table(
        "user_permission_overrides",
        sa.column("id", sa.Integer),
        sa.column("user_id", sa.Integer),
        sa.column("feature_code", sa.String),
        sa.column("effect", sa.String),
    )

    rows = bind.execute(
        sa.select(users.c.id, overrides.c.effect)
        .select_from(users.outerjoin(
            overrides,
            sa.and_(
                overrides.c.user_id == users.c.id,
                overrides.c.feature_code == HISTORY_FEATURE,
            ),
        ))
        .where(users.c.role == "agent")
    ).all()

    # The unified setting cannot restore the former independent choices.
    # On downgrade, apply the unified decision to all three legacy features so
    # a denied Agent remains denied rather than regaining partial access.
    restored = []
    for user_id, unified_effect in rows:
        # Agents created after this migration may have no override row. Their
        # unified role default is Deny, so preserve that on rollback too.
        effect = unified_effect or "deny"
        restored.extend(
            {"user_id": user_id, "feature_code": feature_code, "effect": effect}
            for feature_code in LEGACY_DEFAULTS
        )
    bind.execute(sa.delete(overrides).where(overrides.c.feature_code == HISTORY_FEATURE))
    if restored:
        bind.execute(sa.insert(overrides), restored)
