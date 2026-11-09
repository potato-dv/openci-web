from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.models.activity import ActivityLog
from app.models.agent_revisit import AgentRevisitRequest
from app.models.agent_schedule import AgentWeeklySchedule, AgentWorkProfile, PlanningTrigger
from app.models.assignment import InvestigationAssignment
from app.models.investigation import Investigation
from app.models.planning import AgentShift, PlanningRun
from app.models.realtime_outbox import RealtimeOutboxEvent
from app.models.report import InvestigationReport
from app.models.route_event import InvestigationRouteEvent
from app.models.user import User
from app.models.user_permission_override import UserPermissionOverride
from app.realtime.event_mapping import EventSpec, MANAGER_ROLES, clean_ids


def _changed(obj: object, field: str) -> bool:
    attributes = inspect(obj).attrs
    return field in attributes and attributes[field].history.has_changes()


def _old_value(obj: object, field: str):
    history = inspect(obj).attrs[field].history
    return history.deleted[0] if history.deleted else getattr(obj, field, None)


def _new_specs(obj: object, operation: str) -> list[EventSpec]:
    if isinstance(obj, Investigation):
        if operation == "new":
            users = clean_ids(obj.assigned_agent_id)
            return [EventSpec("investigation.created", "investigation", obj.id or 0, obj.id, users, tuple(MANAGER_ROLES))]
        if operation == "delete":
            specs = [
                EventSpec("investigation.deleted", "investigation", obj.id, obj.id, clean_ids(obj.assigned_agent_id), tuple(MANAGER_ROLES)),
                EventSpec("route.cancelled", "investigation", obj.id, obj.id, clean_ids(obj.assigned_agent_id), tuple(MANAGER_ROLES)),
            ]
            if obj.assigned_agent_id is not None:
                specs.append(EventSpec("route.agent_updated", "agent_route", obj.assigned_agent_id, None, clean_ids(obj.assigned_agent_id)))
            return specs

        old_agent = _old_value(obj, "assigned_agent_id")
        event_types: list[str] = []
        if _changed(obj, "deleted_at"):
            event_types.append("investigation.deleted" if obj.deleted_at is not None else "investigation.restored")
        if _changed(obj, "assigned_agent_id"):
            event_types.append("investigation.unassigned" if obj.assigned_agent_id is None else "investigation.assigned")
        if _changed(obj, "status"):
            event_types.append("investigation.status_changed")
            if obj.status == "cancelled":
                event_types.append("route.cancelled")
        if _changed(obj, "priority"):
            event_types.append("investigation.priority_changed")
        location_fields = (
            "legacy_address", "house_number", "unit_floor_building_name", "street", "postal_code",
            "subdivision_village_purok", "region_code", "province_code", "city_municipality_code",
            "barangay_code", "latitude", "longitude", "location_confirmed_at", "location_source",
            "location_provider_ref",
        )
        detail_fields = (
            "reference_number", "legacy_subject_name", "first_name", "middle_name", "last_name",
            "visit_due_at", "visit_not_before_at", "service_duration_seconds", "notes",
        )
        if any(_changed(obj, field) for field in location_fields):
            event_types.append("investigation.location_updated")
        if any(_changed(obj, field) for field in detail_fields):
            event_types.append("investigation.updated")
        users = clean_ids(obj.assigned_agent_id)
        specs = [EventSpec(kind, "investigation", obj.id, obj.id, users, tuple(MANAGER_ROLES)) for kind in event_types]
        # Agents losing a case or finishing it may no longer be allowed to subscribe
        # to that investigation. Give each affected agent a content-free route
        # invalidation that contains no investigation identifier.
        if any(_changed(obj, field) for field in ("assigned_agent_id", "status", "deleted_at")):
            route_users = clean_ids(old_agent) if _changed(obj, "assigned_agent_id") else users
            specs.extend(
                EventSpec("route.agent_updated", "agent_route", agent_id, None, (agent_id,))
                for agent_id in route_users
            )
        return specs

    if isinstance(obj, InvestigationReport):
        if operation == "new":
            if obj.status != "submitted":
                return []
            return [EventSpec("report.submitted", "investigation_report", obj.id or 0, obj.investigation_id, clean_ids(obj.author_id), tuple(MANAGER_ROLES))]
        if operation == "delete":
            return []
        if _changed(obj, "status"):
            current = obj.status
            if current == "submitted":
                event_types = ["report.submitted"]
            elif current == "returned_for_correction":
                event_types = ["report.reviewed", "report.returned_for_correction"]
            elif current == "approved":
                event_types = ["report.reviewed", "report.completed"]
            else:
                event_types = ["report.reviewed"]
            return [EventSpec(event_type, "investigation_report", obj.id, obj.investigation_id, clean_ids(obj.author_id), tuple(MANAGER_ROLES)) for event_type in event_types]
        if obj.status == "submitted" and any(_changed(obj, field) for field in ("content", "visit_outcome", "outcome", "verified_address", "occupancy_status", "property_condition", "interaction_notes", "visited_at")):
            return [EventSpec("report.updated", "investigation_report", obj.id, obj.investigation_id, clean_ids(obj.author_id), tuple(MANAGER_ROLES))]
        return []

    if isinstance(obj, InvestigationAssignment):
        if operation == "new" and obj.is_active:
            return [
                EventSpec("investigation.assigned", "investigation", obj.investigation_id, obj.investigation_id, clean_ids(obj.agent_id), tuple(MANAGER_ROLES)),
                EventSpec("route.agent_updated", "agent_route", obj.agent_id, None, clean_ids(obj.agent_id)),
            ]
        if operation == "delete" or (operation == "dirty" and _changed(obj, "is_active") and not obj.is_active):
            return [
                EventSpec("investigation.unassigned", "investigation", obj.investigation_id, obj.investigation_id, clean_ids(obj.agent_id), tuple(MANAGER_ROLES)),
                EventSpec("route.agent_updated", "agent_route", obj.agent_id, None, clean_ids(obj.agent_id)),
            ]
        if operation == "dirty" and any(_changed(obj, field) for field in (
            "auto_route_status", "auto_route_work_date", "auto_route_agent_ids", "auto_route_run_ids", "auto_route_errors",
        )):
            affected_agents = clean_ids(obj.agent_id, *(obj.auto_route_agent_ids or []))
            return [
                EventSpec("route.agent_updated", "investigation", obj.investigation_id, obj.investigation_id, (), tuple(MANAGER_ROLES)),
                *(
                    EventSpec("route.agent_updated", "agent_route", agent_id, None, (agent_id,))
                    for agent_id in affected_agents
                ),
            ]
        return []

    if isinstance(obj, PlanningRun):
        if operation == "new":
            agents = obj.agent_ids if isinstance(obj.agent_ids, list) else []
            return [EventSpec("route.updated", "planning_run", obj.id or 0, None, clean_ids(*agents), tuple(MANAGER_ROLES))]
        if operation != "dirty" or not _changed(obj, "status"):
            return []
        if obj.status == "applied":
            event_type = "route.replanned" if obj.auto_replan_requested else "route.published"
        elif obj.status == "stale":
            event_type = "route.replanned"
        elif obj.status == "failed":
            event_type = "route.updated"
        elif obj.status in {"queued", "running", "ready"}:
            event_type = "route.updated"
        else:
            return []
        agents = obj.agent_ids if isinstance(obj.agent_ids, list) else []
        return [EventSpec(event_type, "planning_run", obj.id, None, clean_ids(*agents), tuple(MANAGER_ROLES))]

    if isinstance(obj, AgentShift):
        if operation == "delete":
            kind = "shift.updated"
        elif operation == "new":
            kind = "shift.activated" if obj.is_available else "shift.updated"
        elif _changed(obj, "is_available"):
            kind = "shift.activated" if obj.is_available else "shift.expired"
        elif any(_changed(obj, field) for field in ("shift_starts_at", "shift_ends_at", "region_code", "max_visits", "max_open_cases", "start_latitude", "start_longitude", "end_latitude", "end_longitude")):
            kind = "shift.updated"
        else:
            return []
        return [EventSpec(kind, "agent_shift", getattr(obj, "id", None) or 0, None, clean_ids(obj.agent_id), tuple(MANAGER_ROLES))]

    if isinstance(obj, (AgentWorkProfile, AgentWeeklySchedule)):
        if operation == "delete" or operation == "new" or operation == "dirty":
            return [EventSpec("schedule.updated", "agent_schedule", getattr(obj, "id", None) or 0, None, clean_ids(obj.agent_id), tuple(MANAGER_ROLES))]

    if isinstance(obj, PlanningTrigger):
        if operation in {"new", "dirty", "delete"}:
            return [EventSpec("route.replanned", "planning_trigger", getattr(obj, "id", None) or 0, None, (), tuple(MANAGER_ROLES))]

    if isinstance(obj, AgentRevisitRequest):
        if operation in {"new", "dirty", "delete"}:
            return [EventSpec("investigation.revisit_updated", "investigation", obj.investigation_id, obj.investigation_id, clean_ids(obj.agent_id), tuple(MANAGER_ROLES))]

    if isinstance(obj, InvestigationRouteEvent):
        if operation in {"new", "dirty", "delete"}:
            return [EventSpec("route.agent_updated", "investigation", obj.investigation_id, obj.investigation_id, clean_ids(obj.agent_id), tuple(MANAGER_ROLES))]

    if isinstance(obj, User):
        if operation == "new":
            return [EventSpec("user.created", "user", obj.id or 0, None, clean_ids(obj.id), ("admin",))]
        if operation == "dirty":
            events: list[str] = []
            if _changed(obj, "role"):
                events.append("user.role_changed")
            if _changed(obj, "is_active"):
                events.append("user.activated" if obj.is_active else "user.deactivated")
            return [EventSpec(kind, "user", obj.id, None, clean_ids(obj.id), ("admin",)) for kind in events]

    if isinstance(obj, UserPermissionOverride):
        return [EventSpec("user.permissions_changed", "user", obj.user_id, None, clean_ids(obj.user_id), ("admin",))]

    if isinstance(obj, ActivityLog) and operation == "new":
        return [EventSpec("activity.created", "activity_log", obj.id or 0, None, (), ("admin",))]

    return []


def before_flush(session: Session, _flush_context, _instances) -> None:
    if session.info.get("realtime_outbox_writing"):
        return
    specs: list[tuple[object, EventSpec]] = []
    for obj in tuple(session.new):
        specs.extend((obj, spec) for spec in _new_specs(obj, "new"))
    for obj in tuple(session.dirty):
        if obj not in session.new and session.is_modified(obj, include_collections=False):
            specs.extend((obj, spec) for spec in _new_specs(obj, "dirty"))
    for obj in tuple(session.deleted):
        specs.extend((obj, spec) for spec in _new_specs(obj, "delete"))
    session.info["realtime_pending_specs"] = specs


def after_flush_postexec(session: Session, _flush_context) -> None:
    specs = session.info.pop("realtime_pending_specs", [])
    if not specs:
        return
    seen: set[tuple[str, str, int | None]] = set()
    session.info["realtime_outbox_writing"] = True
    try:
        for obj, spec in specs:
            entity_id = spec.entity_id or getattr(obj, "id", None)
            if not entity_id:
                continue
            investigation_id = spec.investigation_id
            if investigation_id is None and isinstance(obj, Investigation) and spec.entity_type == "investigation":
                investigation_id = obj.id
            key = (spec.event_type, str(entity_id), investigation_id)
            if key in seen:
                continue
            seen.add(key)
            session.add(RealtimeOutboxEvent(
                event_id=uuid4(),
                event_type=spec.event_type,
                entity_type=spec.entity_type,
                entity_id=str(entity_id),
                investigation_id=investigation_id,
                recipient_user_ids=list(spec.recipient_user_ids),
                recipient_roles=list(spec.recipient_roles),
                occurred_at=datetime.now(timezone.utc),
                available_at=datetime.now(timezone.utc),
            ))
    finally:
        session.info.pop("realtime_outbox_writing", None)


def register_orm_event_listeners() -> None:
    if not event.contains(Session, "before_flush", before_flush):
        event.listen(Session, "before_flush", before_flush)
    if not event.contains(Session, "after_flush_postexec", after_flush_postexec):
        event.listen(Session, "after_flush_postexec", after_flush_postexec)
