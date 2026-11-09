from __future__ import annotations

from dataclasses import dataclass


MANAGER_ROLES = ["admin", "supervisor"]


@dataclass(frozen=True)
class EventSpec:
    event_type: str
    entity_type: str
    entity_id: int | str
    investigation_id: int | None = None
    recipient_user_ids: tuple[int, ...] = ()
    recipient_roles: tuple[str, ...] = ()


def clean_ids(*values: object) -> tuple[int, ...]:
    return tuple(sorted({value for value in values if isinstance(value, int) and value > 0}))


def manager_recipients(*user_ids: object) -> tuple[tuple[int, ...], tuple[str, ...]]:
    return clean_ids(*user_ids), tuple(MANAGER_ROLES)


def event_scope_names(event_type: str) -> tuple[str, ...]:
    """Scopes capable of receiving a notification of this type.

    The audience attached to each outbox event is checked separately, so this
    table never grants a user access to the entity represented by an event.
    """
    if event_type.startswith("report."):
        return ("reports.queue", "investigations", "dashboard", "me")
    if event_type.startswith("investigation."):
        return ("investigations", "route.planning", "route.own", "dashboard", "me")
    if event_type.startswith("route."):
        return ("route.planning", "route.own", "dashboard", "me")
    if event_type.startswith("activity."):
        return ("activity.logs",)
    if event_type.startswith("user."):
        return ("users", "me")
    if event_type.startswith(("schedule.", "shift.")):
        return ("schedules", "route.planning", "route.own", "dashboard", "me")
    return ()
