import json
from collections.abc import Mapping
from typing import Any

from app.schemas.activity import ActivityLogDetail


USER_ID_KEYS = {
    "agent_id",
    "assigned_agent_id",
    "previous_agent_id",
    "reviewer_id",
    "user_id",
}
SENSITIVE_KEY_PARTS = {
    "address",
    "content",
    "coordinate",
    "latitude",
    "longitude",
    "note",
    "password",
    "secret",
    "token",
}
SAFE_NESTED_KEYS = {
    "new_effective",
    "new_overrides",
    "old_effective",
    "old_overrides",
}


def humanize(value: str) -> str:
    return value.replace(".", " ").replace("_", " ").strip().capitalize()


def action_label(action: str) -> str:
    return " ".join(humanize(part) for part in action.split("."))


def related_user_ids(details: Mapping[str, Any]) -> set[int]:
    return {
        value
        for key, value in details.items()
        if key in USER_ID_KEYS and isinstance(value, int) and value > 0
    }


def _sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def _format_value(
    key: str,
    value: Any,
    related_users: Mapping[int, str],
) -> tuple[str, bool]:
    if _sensitive(key):
        return "Value hidden", True

    if key in USER_ID_KEYS and isinstance(value, int):
        return related_users.get(value, f"User #{value}"), False

    if key == "fields" and isinstance(value, list):
        return ", ".join(humanize(str(item)) for item in value), False

    if isinstance(value, bool):
        return ("Yes" if value else "No"), False
    if value is None:
        return "None", False
    if isinstance(value, (str, int, float)):
        return str(value), False
    if isinstance(value, (dict, list)):
        if key not in SAFE_NESTED_KEYS:
            return "Structured value hidden", True
        return json.dumps(value, sort_keys=True, separators=(", ", ": ")), False
    return str(value), False


def detail_fields(
    details: Mapping[str, Any],
    related_users: Mapping[int, str] | None = None,
) -> list[ActivityLogDetail]:
    related_users = related_users or {}
    return [
        ActivityLogDetail(
            key=key,
            label=humanize(key),
            value=value,
            redacted=redacted,
        )
        for key, raw_value in details.items()
        for value, redacted in [_format_value(key, raw_value, related_users)]
    ]


def _related_name(
    details: Mapping[str, Any],
    key: str,
    related_users: Mapping[int, str],
) -> str:
    value = details.get(key)
    if isinstance(value, int):
        return related_users.get(value, f"User #{value}")
    return "an unknown user"


def record_label(
    object_type: str,
    object_id: int | None,
    resolved_labels: Mapping[tuple[str, int], str] | None = None,
) -> str:
    if object_id is None:
        return humanize(object_type)
    if resolved_labels and (object_type, object_id) in resolved_labels:
        return resolved_labels[(object_type, object_id)]
    return f"{humanize(object_type)} ID: {object_id} (record unavailable)"


def summarize_activity(    action: str,
    details: Mapping[str, Any] | None = None,
    related_users: Mapping[int, str] | None = None,
) -> str:
    details = details or {}
    related_users = related_users or {}

    if action == "user.created" and isinstance(details.get("role"), str):
        return f"Account created with {humanize(details['role'])} role"
    if action == "user.activation_changed" and isinstance(details.get("is_active"), bool):
        return f"Account {'activated' if details['is_active'] else 'deactivated'}"
    if action == "user.role_changed":
        before = details.get("from")
        after = details.get("to")
        if isinstance(before, str) and isinstance(after, str):
            return f"Role changed from {humanize(before)} to {humanize(after)}"
    if action == "investigation.assigned" and "agent_id" in details:
        return f"Investigation assigned to {_related_name(details, 'agent_id', related_users)}"
    if action == "investigation.unassigned":
        return "Investigation unassigned"
    if action == "investigation.updated" and isinstance(details.get("fields"), list):
        fields = [humanize(str(field)) for field in details["fields"]]
        return f"Investigation updated: {', '.join(fields)}" if fields else "Investigation updated"
    if action == "report.reviewed" and isinstance(details.get("decision"), str):
        return f"Report review: {humanize(details['decision'])}"
    if action == "investigation.location_confirmed":
        return "Investigation location confirmed"
    if action == "investigation.revisit_requested":
        return "Investigation revisit requested"
    if action == "agent.permissions_changed":
        return "Agent permissions changed"
    if action == "investigation.automatic_assignment_requested":
        return "Automatic assignment requested"
    if action == "investigation.restored":
        return "Investigation restored from Trash"
    if action == "investigation.deleted":
        return "Investigation moved to Trash"
    if action == "investigation.permanently_deleted":
        return "Investigation permanently deleted"

    return action_label(action)
