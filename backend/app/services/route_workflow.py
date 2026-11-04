"""Mandatory agent route sequencing and separately audited visit attempts."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.activity import ActivityLog
from app.models.assignment import InvestigationAssignment
from app.models.investigation import Investigation
from app.models.planning import AgentShift, PlanningItem, PlanningRun
from app.models.report import InvestigationReport
from app.models.route_event import InvestigationRouteEvent
from app.models.user import User

MANILA = ZoneInfo("Asia/Manila")
ACTIVE_INVESTIGATION_STATUSES = ("pending", "assigned", "in_progress", "returned_for_correction")
NO_CONTACT_REASONS = {
    "no_contact_person",
    "nobody_at_location",
    "requested_later_visit",
    "other",
}


class RouteActionConflict(ValueError):
    """An agent action conflicts with the currently published route state."""


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _current_date(now: datetime | None = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(MANILA).date()


def _route_snapshot(
    db: Session,
    agent_id: int,
    work_date: date,
    *,
    now: datetime | None = None,
    lock_shift: bool = False,
) -> dict:
    shift_query = db.query(AgentShift).filter(
        AgentShift.agent_id == agent_id,
        AgentShift.work_date == work_date,
    )
    if lock_shift:
        shift_query = shift_query.with_for_update()
    shift = shift_query.first()
    run = db.get(PlanningRun, shift.current_planning_run_id) if shift and shift.current_planning_run_id else None
    if run is not None and run.status != "applied":
        run = None

    in_progress_cases = db.query(Investigation).filter(
        Investigation.assigned_agent_id == agent_id,
        Investigation.deleted_at.is_(None),
        Investigation.status == "in_progress",
    ).order_by(Investigation.id).all()
    if run is None:
        active_case_ids = [
            case_id for (case_id,) in db.query(Investigation.id).filter(
                Investigation.assigned_agent_id == agent_id,
                Investigation.deleted_at.is_(None),
                Investigation.status.in_(ACTIVE_INVESTIGATION_STATUSES),
            ).all()
        ]
        event_case_ids = [
            case_id for (case_id,) in db.query(InvestigationRouteEvent.investigation_id).filter(
                InvestigationRouteEvent.agent_id == agent_id,
                InvestigationRouteEvent.work_date == work_date,
            ).distinct().all()
        ]
        active_case_ids = sorted(set(active_case_ids) | set(event_case_ids))
    else:
        active_case_ids = []
    if run is None and active_case_ids:
        run = db.query(PlanningRun).join(
            PlanningItem, PlanningItem.planning_run_id == PlanningRun.id,
        ).filter(
            PlanningRun.work_date == work_date,
            PlanningRun.status == "applied",
            PlanningItem.agent_id == agent_id,
            PlanningItem.investigation_id.in_(active_case_ids),
            PlanningItem.outcome == "assigned",
        ).order_by(PlanningRun.id.desc()).first()

    rows = []
    if run is not None:
        rows = db.query(PlanningItem, Investigation).join(
            Investigation, Investigation.id == PlanningItem.investigation_id,
        ).filter(
            PlanningItem.planning_run_id == run.id,
            PlanningItem.agent_id == agent_id,
            PlanningItem.outcome == "assigned",
            Investigation.assigned_agent_id == agent_id,
            Investigation.deleted_at.is_(None),
            Investigation.status != "cancelled",
        ).order_by(PlanningItem.sequence, PlanningItem.investigation_id).all()

    case_ids = [case.id for _item, case in rows]
    planned_case_ids = set()
    if run is not None:
        planned_case_ids = {
            case_id for (case_id,) in db.query(PlanningItem.investigation_id).join(
                Investigation, Investigation.id == PlanningItem.investigation_id,
            ).filter(
                PlanningItem.planning_run_id == run.id,
                PlanningItem.agent_id == agent_id,
                PlanningItem.outcome == "assigned",
                Investigation.deleted_at.is_(None),
                Investigation.status != "cancelled",
            ).all()
        }
    expected_open_query = db.query(Investigation.id).filter(
        Investigation.assigned_agent_id == agent_id,
        Investigation.deleted_at.is_(None),
        Investigation.status.in_(ACTIVE_INVESTIGATION_STATUSES),
        Investigation.location_confirmed_at.is_not(None),
        Investigation.latitude.is_not(None),
        Investigation.longitude.is_not(None),
    )
    if shift is not None:
        if shift.region_code == "ALL":
            from app.services.locations import catalog

            expected_open_query = expected_open_query.filter(Investigation.region_code.in_(catalog()["region_codes"]))
        else:
            expected_open_query = expected_open_query.filter(Investigation.region_code == shift.region_code)
    expected_open_case_ids = {case_id for (case_id,) in expected_open_query.all()}
    route_matches_assignments = bool(
        run is not None
        and set(case_ids) == planned_case_ids
        and expected_open_case_ids.issubset(set(case_ids))
    )
    has_unrouted_open_work = bool(expected_open_case_ids - set(case_ids))
    events = db.query(InvestigationRouteEvent).filter(
        InvestigationRouteEvent.agent_id == agent_id,
        InvestigationRouteEvent.work_date == work_date,
    ).order_by(InvestigationRouteEvent.attempted_at, InvestigationRouteEvent.id).all()
    root_events = [event for event in events if event.event_type == "no_contact" and event.parent_event_id is None and event.retry_number == 0]
    children_by_parent: dict[int, list[InvestigationRouteEvent]] = {}
    for event in events:
        if event.parent_event_id is not None:
            children_by_parent.setdefault(event.parent_event_id, []).append(event)

    now_utc = _aware(now or datetime.now(timezone.utc))
    row_by_case = {case.id: (item, case) for item, case in rows}
    active = [row_by_case.get(case.id, (None, case)) for case in in_progress_cases]
    primary = []
    for item, case in rows:
        if case.status not in ACTIVE_INVESTIGATION_STATUSES:
            continue
        if any(
            event.investigation_id == case.id
            and event.event_type == "shift_end_not_visited"
            and event.state == "carried_over"
            for event in events
        ):
            continue
        root = next((event for event in root_events if event.investigation_id == case.id), None)
        if root is not None and root.state in {"deferred", "retrying", "retry_failed", "carried_over", "resolved"}:
            continue
        primary.append((item, case))

    current_id: int | None = None
    current_kind: str | None = None
    current_event: InvestigationRouteEvent | None = None
    can_start = False
    can_report = False
    can_finalize_event: InvestigationRouteEvent | None = None
    retryable_roots: list[InvestigationRouteEvent] = []

    if active:
        current_item, current_case = active[0]
        current_id = current_case.id
        current_kind = "current"
        can_report = True
        root = next((event for event in root_events if event.investigation_id == current_case.id), None)
        if root and root.state == "retrying":
            current_kind = "deferred_retry"
            current_event = next((event for event in children_by_parent.get(root.id, []) if event.state == "retrying"), root)
    elif route_matches_assignments and primary:
        current_item, current_case = primary[0]
        current_id = current_case.id
        current_kind = "current"
    elif route_matches_assignments and run is not None and shift is not None:
        retryable_roots = [
            root for root in root_events
            if root.state == "deferred"
            and not children_by_parent.get(root.id)
            and db.get(Investigation, root.investigation_id) is not None
        ]
        retryable_roots.sort(key=lambda event: _retry_sort_key(db, event))
        for root in retryable_roots:
            case = db.get(Investigation, root.investigation_id)
            if case is not None and case.assigned_agent_id == agent_id and _retry_feasible(db, shift, case, root, now_utc):
                current_id = case.id
                current_kind = "deferred_retry"
                current_event = root
                break
        if current_id is None:
            failed = [
                event for event in events
                if event.event_type == "no_contact"
                and event.state == "retry_failed"
                and db.get(Investigation, event.investigation_id) is not None
                and (
                    db.get(Investigation, event.investigation_id).assigned_agent_id == agent_id
                    or db.get(Investigation, event.investigation_id).assigned_agent_id is None
                )
            ]
            if failed and not has_unrouted_open_work:
                # Finalize the most recent failed attempt (a retry child when
                # one exists), matching the event shown as the latest history.
                can_finalize_event = sorted(
                    failed,
                    key=lambda event: (event.attempted_at, event.id),
                    reverse=True,
                )[0]
            else:
                expired_or_infeasible = []
                for root in retryable_roots:
                    case = db.get(Investigation, root.investigation_id)
                    if case is not None and (
                        case.assigned_agent_id == agent_id and not _retry_feasible(db, shift, case, root, now_utc)
                        or case.assigned_agent_id is None and _aware(shift.shift_ends_at) <= now_utc
                    ):
                        expired_or_infeasible.append(root)
                if expired_or_infeasible and not has_unrouted_open_work:
                    can_finalize_event = expired_or_infeasible[0]

    if current_id is not None and current_kind == "current":
        case = next((case for _item, case in active + primary if case.id == current_id), None)
        shift_start = _aware(shift.shift_starts_at) if shift else None
        shift_end = _aware(shift.shift_ends_at) if shift else None
        is_today = work_date == _current_date(now_utc)
        can_start = bool(
            case is not None
            and case.status != "in_progress"
            and shift is not None
            and shift.is_available
            and is_today
            and shift_start is not None and shift_start <= now_utc
            and shift_end is not None and now_utc < shift_end
        )
    elif current_id is not None and current_kind == "deferred_retry":
        shift_start = _aware(shift.shift_starts_at) if shift else None
        shift_end = _aware(shift.shift_ends_at) if shift else None
        is_today = work_date == _current_date(now_utc)
        available_from = max(
            (_aware(value) for value in (
                current_event.contact_available_from if current_event else None,
                db.get(Investigation, current_id).visit_not_before_at if db.get(Investigation, current_id) else None,
            ) if value is not None),
            default=None,
        )
        can_start = bool(
            shift is not None and shift.is_available and is_today
            and shift_start is not None and shift_start <= now_utc
            and shift_end is not None and now_utc < shift_end
            and (available_from is None or now_utc >= available_from)
        )

    attempt_case_ids = sorted(set(case_ids) | {event.investigation_id for event in events})
    history = []
    if attempt_case_ids:
        history = db.query(InvestigationRouteEvent, Investigation).join(
            Investigation, Investigation.id == InvestigationRouteEvent.investigation_id,
        ).filter(
            InvestigationRouteEvent.investigation_id.in_(attempt_case_ids),
        ).order_by(InvestigationRouteEvent.attempted_at.desc(), InvestigationRouteEvent.id.desc()).all()

    history_by_case: dict[int, list[dict]] = {}
    for event, case in history:
        history_by_case.setdefault(event.investigation_id, []).append({
            "id": event.id,
            "investigation_id": event.investigation_id,
            "reference_number": case.reference_number,
            "address_display": case.address_display,
            "priority": case.priority,
            "agent_id": event.agent_id,
            "work_date": event.work_date,
            "planning_run_id": event.planning_run_id,
            "parent_event_id": event.parent_event_id,
            "event_type": event.event_type,
            "state": event.state,
            "retry_number": event.retry_number,
            "reason": event.reason,
            "notes": event.notes,
            "contact_available_from": event.contact_available_from,
            "contact_available_until": event.contact_available_until,
            "attempted_at": event.attempted_at,
            "next_work_date": event.next_work_date,
            "finalized_at": event.finalized_at,
        })

    deferred = []
    for case_id, attempt_list in history_by_case.items():
        latest = next((entry for entry in attempt_list if entry["work_date"] == work_date and entry["agent_id"] == agent_id), None)
        if latest and latest["event_type"] in {"no_contact", "shift_end_not_visited"} and latest["state"] not in {"resolved"}:
            latest["can_finalize_no_contact"] = bool(
                can_finalize_event and can_finalize_event.id == latest["id"]
            )
            latest["retry_actionable"] = bool(
                current_id == case_id and current_kind == "deferred_retry" and can_start
            )
            deferred.append(latest)

    stop_states = {}
    for _item, case in rows:
        if case.status in {"under_review", "completed", "cancelled"}:
            state = "handled"
        elif case.id == current_id:
            state = current_kind or "current"
        elif any(event.investigation_id == case.id and event.event_type == "shift_end_not_visited" and event.state == "carried_over" for event in events):
            state = "deferred"
        elif any(root.investigation_id == case.id and root.state in {"deferred", "retrying", "retry_failed", "carried_over"} for root in root_events):
            state = "deferred"
        else:
            state = "upcoming"
        stop_states[case.id] = {
            "sequence_state": state,
            "actionable": case.id == current_id,
            "can_start": case.id == current_id and can_start,
            "can_report": case.id == current_id and can_report,
            "active_attempt_id": (
                current_event.id if current_event and current_event.investigation_id == case.id
                else can_finalize_event.id if can_finalize_event and can_finalize_event.investigation_id == case.id
                else None
            ),
            "can_finalize_no_contact": bool(can_finalize_event and can_finalize_event.investigation_id == case.id and can_finalize_event.id),
            "priority_order_exception_reason": _priority_exception_for(run, case.id),
            "attempt_history": history_by_case.get(case.id, []),
        }
    for _item, case in active:
        stop_states.setdefault(case.id, {
            "sequence_state": "current",
            "actionable": case.id == current_id,
            "can_start": False,
            "can_report": case.id == current_id,
            "active_attempt_id": current_event.id if current_event and current_event.investigation_id == case.id else None,
            "can_finalize_no_contact": False,
            "priority_order_exception_reason": _priority_exception_for(run, case.id),
            "attempt_history": history_by_case.get(case.id, []),
        })

    return {
        "shift": shift,
        "run": run,
        "route_revision": run.id if run is not None else None,
        "route_matches_assignments": route_matches_assignments,
        "has_unrouted_open_work": has_unrouted_open_work,
        "current_actionable_investigation_id": current_id,
        "current_actionable_kind": current_kind,
        "current_event": current_event,
        "can_start": can_start,
        "can_report": can_report,
        "can_finalize_event": can_finalize_event,
        "stop_states": stop_states,
        "attempt_history": [entry for values in history_by_case.values() for entry in values],
        "deferred_attempts": deferred,
        "priority_order_warnings": [
            warning for warning in (run.warnings or [])
            if warning.get("type") == "priority_order" and warning.get("agent_id") == agent_id
        ] if run is not None else [],
    }


def route_workflow_snapshot(
    db: Session,
    agent_id: int,
    work_date: date,
    now: datetime | None = None,
) -> dict:
    return _route_snapshot(db, agent_id, work_date, now=now)


def _priority_rank(priority: str | None) -> int:
    return {"urgent": 0, "high": 1, "normal": 2}.get(priority or "normal", 2)


def _retry_sort_key(db: Session, event: InvestigationRouteEvent) -> tuple:
    case = db.get(Investigation, event.investigation_id)
    return (
        _priority_rank(case.priority if case else "normal"),
        _original_assignment_at(db, event.investigation_id),
        event.investigation_id,
    )


def _original_assignment_at(db: Session, investigation_id: int) -> datetime:
    assigned_at = db.query(InvestigationAssignment.assigned_at).filter(
        InvestigationAssignment.investigation_id == investigation_id,
    ).order_by(InvestigationAssignment.assigned_at, InvestigationAssignment.id).first()
    case = db.get(Investigation, investigation_id)
    return _aware(assigned_at[0] if assigned_at else case.created_at if case else None) or datetime.max.replace(tzinfo=timezone.utc)


def _priority_exception_for(run: PlanningRun | None, investigation_id: int) -> str | None:
    if run is None:
        return None
    for warning in run.warnings or []:
        if warning.get("type") == "priority_order" and (
            warning.get("investigation_id") == investigation_id
            or warning.get("deferred_investigation_id") == investigation_id
        ):
            return warning.get("reason")
    return None


def _retry_feasible(
    db: Session,
    shift: AgentShift,
    case: Investigation,
    event: InvestigationRouteEvent,
    now: datetime,
) -> bool:
    if shift.work_date != _current_date(now) or not shift.is_available:
        return False
    shift_start = _aware(shift.shift_starts_at)
    shift_end = _aware(shift.shift_ends_at)
    if shift_start is None or shift_end is None or now >= shift_end:
        return False
    if case.latitude is None or case.longitude is None:
        return False

    origin = None
    completed_at = _aware(shift.last_completed_at)
    attempt_at = _aware(event.attempted_at)
    if (
        completed_at and completed_at >= (attempt_at or completed_at)
        and shift.last_completed_latitude is not None and shift.last_completed_longitude is not None
    ):
        origin = (shift.last_completed_latitude, shift.last_completed_longitude)
    elif event.latitude is not None and event.longitude is not None:
        origin = (event.latitude, event.longitude)
    else:
        origin = (shift.start_latitude, shift.start_longitude)

    travel_seconds = None
    try:
        from app.services.routing import OSRMClient, RoutingUnavailable

        osrm = OSRMClient()
        try:
            matrix = osrm.table([origin, (case.latitude, case.longitude)])
            durations = matrix.get("durations")
            if isinstance(durations, list) and len(durations) == 2 and isinstance(durations[0], list):
                travel = durations[0][1]
                if isinstance(travel, (int, float)) and travel >= 0:
                    travel_seconds = int(travel)
        finally:
            osrm.client.close()
    except (RuntimeError, ValueError, KeyError, TypeError):
        travel_seconds = None
    except Exception:
        travel_seconds = None
    if travel_seconds is None:
        return False

    departure = max(now, shift_start)
    break_start = _aware(shift.break_starts_at)
    break_end = _aware(shift.break_ends_at)
    if break_start and break_end and departure < break_start and departure + timedelta(seconds=travel_seconds) > break_start:
        departure = break_end
    elif break_start and break_end and break_start <= departure < break_end:
        departure = break_end
    arrival = departure + timedelta(seconds=travel_seconds)
    service_start = max(arrival, _aware(case.visit_not_before_at) or arrival)
    if break_start and break_end:
        if break_start <= service_start < break_end:
            service_start = break_end
        elif service_start < break_start < service_start + timedelta(seconds=case.service_duration_seconds):
            service_start = break_end
    service_end = service_start + timedelta(seconds=case.service_duration_seconds)
    if service_end > shift_end:
        return False
    visit_due = _aware(case.visit_due_at)
    if visit_due and service_end > visit_due:
        return False
    available_from = _aware(event.contact_available_from)
    available_until = _aware(event.contact_available_until)
    if available_from and service_start < available_from:
        service_start = available_from
        if break_start and break_end and break_start < service_start < break_end:
            service_start = break_end
        service_end = service_start + timedelta(seconds=case.service_duration_seconds)
    if available_until and service_end > available_until:
        return False
    return service_end <= shift_end and (visit_due is None or service_end <= visit_due)


def assert_current_action(
    db: Session,
    investigation: Investigation,
    actor: User,
    work_date: date,
    route_revision: int,
    *,
    require_started: bool = False,
    now: datetime | None = None,
) -> dict:
    if actor.role != "agent" or investigation.assigned_agent_id != actor.id:
        raise RouteActionConflict("This investigation is no longer assigned to you.")
    state = _route_snapshot(db, actor.id, work_date, now=now, lock_shift=True)
    if state["route_revision"] is None:
        raise RouteActionConflict("Your current route is not published. Refresh the route before continuing.")
    if state["route_revision"] != route_revision:
        raise RouteActionConflict("Your route changed. Refresh it and continue from the current stop.")
    if not state["route_matches_assignments"] and not (
        investigation.status == "in_progress"
        and state["current_actionable_investigation_id"] == investigation.id
    ):
        raise RouteActionConflict("Your published route is updating. Refresh it before starting this stop.")
    if state["current_actionable_investigation_id"] != investigation.id:
        raise RouteActionConflict("This investigation is out of sequence. Complete or defer the current stop first.")
    if require_started and investigation.status != "in_progress":
        raise RouteActionConflict("Start this current investigation before saving or submitting its report.")
    return state


def start_current_investigation(
    db: Session,
    investigation_id: int,
    actor: User,
    work_date: date,
    route_revision: int,
    now: datetime | None = None,
) -> dict:
    investigation = db.query(Investigation).filter(
        Investigation.id == investigation_id,
        Investigation.deleted_at.is_(None),
    ).with_for_update().first()
    if investigation is None:
        raise RouteActionConflict("Investigation not found.")
    state = assert_current_action(db, investigation, actor, work_date, route_revision, now=now)
    if investigation.status == "in_progress":
        db.commit()
        return {"investigation_id": investigation.id, "route_revision": route_revision, "started": True}
    if investigation.status not in {"assigned", "pending", "returned_for_correction"}:
        raise RouteActionConflict("This investigation cannot be started in its current state.")
    if not state["can_start"]:
        raise RouteActionConflict("This stop cannot be started outside its available shift window.")

    current_event = state["current_event"]
    if state["current_actionable_kind"] == "deferred_retry":
        if current_event is None or current_event.event_type != "no_contact" or current_event.retry_number != 0:
            raise RouteActionConflict("This deferred investigation is no longer eligible for a retry.")
        current_event.state = "retrying"
        child = InvestigationRouteEvent(
            investigation_id=investigation.id,
            agent_id=actor.id,
            work_date=work_date,
            planning_run_id=route_revision,
            parent_event_id=current_event.id,
            event_type="no_contact",
            state="retrying",
            retry_number=1,
            reason="retry_started",
            notes=None,
            attempted_at=now or datetime.now(timezone.utc),
            latitude=investigation.latitude,
            longitude=investigation.longitude,
        )
        db.add(child)
    investigation.status = "in_progress"
    db.add(ActivityLog(
        actor_id=actor.id,
        action="investigation.route_stop_started",
        object_type="investigation",
        object_id=investigation.id,
        details={"work_date": work_date.isoformat(), "planning_run_id": route_revision, "retry": state["current_actionable_kind"] == "deferred_retry"},
    ))
    db.commit()
    return {"investigation_id": investigation.id, "route_revision": route_revision, "started": True}


def record_unable_to_proceed(
    db: Session,
    investigation_id: int,
    actor: User,
    work_date: date,
    route_revision: int,
    reason: str,
    notes: str | None,
    contact_available_from: datetime | None = None,
    contact_available_until: datetime | None = None,
    now: datetime | None = None,
) -> InvestigationRouteEvent:
    if reason not in NO_CONTACT_REASONS:
        raise RouteActionConflict("Choose a valid reason for being unable to proceed.")
    if reason == "other" and not (notes or "").strip():
        raise RouteActionConflict("Add a note when the reason is Other.")
    contact_available_from = _aware(contact_available_from)
    contact_available_until = _aware(contact_available_until)
    if contact_available_from and contact_available_until and contact_available_until <= contact_available_from:
        raise RouteActionConflict("The contact availability end must be after its start.")

    investigation = db.query(Investigation).filter(
        Investigation.id == investigation_id,
        Investigation.deleted_at.is_(None),
    ).with_for_update().first()
    if investigation is None:
        raise RouteActionConflict("Investigation not found.")
    state = assert_current_action(
        db, investigation, actor, work_date, route_revision,
        require_started=True, now=now,
    )
    if not state["can_report"]:
        raise RouteActionConflict("Only an active visit can be deferred.")

    current_time = _aware(now or datetime.now(timezone.utc))
    retry_number = 1 if state["current_actionable_kind"] == "deferred_retry" else 0
    if retry_number == 1:
        event = state["current_event"]
        if event is None or event.retry_number != 1 or event.state != "retrying":
            raise RouteActionConflict("The retry attempt is no longer active.")
        event.state = "retry_failed"
        event.reason = reason
        event.notes = (notes or "").strip() or None
        event.contact_available_from = contact_available_from
        event.contact_available_until = contact_available_until
        event.attempted_at = current_time
        parent = db.get(InvestigationRouteEvent, event.parent_event_id) if event.parent_event_id else None
        if parent is not None:
            parent.state = "retry_failed"
    else:
        event = InvestigationRouteEvent(
            investigation_id=investigation.id,
            agent_id=actor.id,
            work_date=work_date,
            planning_run_id=route_revision,
            parent_event_id=None,
            event_type="no_contact",
            state="deferred",
            retry_number=0,
            reason=reason,
            notes=(notes or "").strip() or None,
            contact_available_from=contact_available_from,
            contact_available_until=contact_available_until,
            attempted_at=current_time,
            latitude=investigation.latitude,
            longitude=investigation.longitude,
        )
        db.add(event)
    shift = state["shift"]
    if shift is not None:
        shift.last_attempted_investigation_id = investigation.id
        shift.last_attempted_at = current_time
        shift.last_attempted_latitude = investigation.latitude
        shift.last_attempted_longitude = investigation.longitude
    investigation.status = "assigned"
    db.add(ActivityLog(
        actor_id=actor.id,
        action="investigation.no_contact_deferred",
        object_type="investigation",
        object_id=investigation.id,
        details={"work_date": work_date.isoformat(), "planning_run_id": route_revision, "reason": reason, "retry_number": retry_number},
    ))
    from app.services.agent_schedules import enqueue_planning_trigger

    enqueue_planning_trigger(db, work_date, investigation.region_code, "agent_no_contact_attempt")
    db.commit()
    db.refresh(event)
    return event


def finalize_no_contact_attempt(
    db: Session,
    event_id: int,
    actor: User,
    work_date: date,
    route_revision: int,
    now: datetime | None = None,
) -> InvestigationRouteEvent:
    event = db.query(InvestigationRouteEvent).filter(
        InvestigationRouteEvent.id == event_id,
        InvestigationRouteEvent.event_type == "no_contact",
        InvestigationRouteEvent.agent_id == actor.id,
        InvestigationRouteEvent.work_date == work_date,
    ).first()
    if event is None:
        raise RouteActionConflict("No unresolved no-contact attempt was found for this route.")
    case = db.query(Investigation).filter(Investigation.id == event.investigation_id).with_for_update().first()
    if case is None:
        raise RouteActionConflict("Investigation not found.")
    event = db.query(InvestigationRouteEvent).filter(
        InvestigationRouteEvent.id == event_id,
        InvestigationRouteEvent.event_type == "no_contact",
        InvestigationRouteEvent.agent_id == actor.id,
        InvestigationRouteEvent.work_date == work_date,
    ).with_for_update().first()
    if event is None or event.state not in {"deferred", "retry_failed"}:
        raise RouteActionConflict("This no-contact attempt is already finalized or changed.")
    state = _route_snapshot(db, actor.id, work_date, now=now, lock_shift=True)
    shift_ended = bool(
        state["shift"]
        and _aware(state["shift"].shift_ends_at) is not None
        and _aware(state["shift"].shift_ends_at) <= _aware(now or datetime.now(timezone.utc))
    )
    if actor.role != "agent" or (
        case.assigned_agent_id != actor.id
        and not (case.assigned_agent_id is None and shift_ended)
    ):
        raise RouteActionConflict("This investigation is no longer assigned to you.")
    if state["route_revision"] != route_revision:
        raise RouteActionConflict("Your route changed. Refresh it and continue from the current stop.")
    if state["can_finalize_event"] is None or state["can_finalize_event"].id != event.id:
        raise RouteActionConflict("Finish the remaining route or use the available retry before carrying this attempt over.")
    event.state = "carried_over"
    event.finalized_at = _aware(now or datetime.now(timezone.utc))
    event.next_work_date = next_valid_work_date(db, actor.id, work_date)
    if event.parent_event_id is not None:
        parent = db.get(InvestigationRouteEvent, event.parent_event_id)
        if parent is not None:
            parent.state = "carried_over"
            parent.finalized_at = event.finalized_at
            parent.next_work_date = event.next_work_date
    db.add(ActivityLog(
        actor_id=actor.id,
        action="investigation.no_contact_report_finalized",
        object_type="investigation",
        object_id=case.id,
        details={"route_event_id": event.id, "work_date": work_date.isoformat(), "next_work_date": event.next_work_date.isoformat() if event.next_work_date else None, "reason": event.reason},
    ))
    # Shift-end processing owns the actual next-day trigger so automatic
    # assignments can first be returned to the shared planning pool.
    db.commit()
    db.refresh(event)
    return event


def next_valid_work_date(db: Session, agent_id: int, after: date) -> date | None:
    from app.services.agent_schedules import resolve_availability_day

    for offset in range(1, 32):
        candidate = after + timedelta(days=offset)
        availability = resolve_availability_day(db, agent_id, candidate)
        if availability.get("is_available") and availability.get("shift_starts_at"):
            return candidate
    return None


def route_attempt_history(db: Session, investigation_ids: list[int]) -> dict[int, list[dict]]:
    if not investigation_ids:
        return {}
    rows = db.query(InvestigationRouteEvent, Investigation).join(
        Investigation, Investigation.id == InvestigationRouteEvent.investigation_id,
    ).filter(InvestigationRouteEvent.investigation_id.in_(investigation_ids)).order_by(
        InvestigationRouteEvent.attempted_at.desc(), InvestigationRouteEvent.id.desc(),
    ).all()
    result: dict[int, list[dict]] = {}
    for event, case in rows:
        result.setdefault(event.investigation_id, []).append({
            "id": event.id,
            "investigation_id": event.investigation_id,
            "reference_number": case.reference_number,
            "address_display": case.address_display,
            "priority": case.priority,
            "agent_id": event.agent_id,
            "work_date": event.work_date,
            "planning_run_id": event.planning_run_id,
            "parent_event_id": event.parent_event_id,
            "event_type": event.event_type,
            "state": event.state,
            "retry_number": event.retry_number,
            "reason": event.reason,
            "notes": event.notes,
            "contact_available_from": event.contact_available_from,
            "contact_available_until": event.contact_available_until,
            "attempted_at": event.attempted_at,
            "next_work_date": event.next_work_date,
            "finalized_at": event.finalized_at,
        })
    return result


def route_agent_event_history(db: Session, agent_id: int, work_date: date) -> list[dict]:
    event_case_ids = [
        case_id for (case_id,) in db.query(InvestigationRouteEvent.investigation_id).filter(
            InvestigationRouteEvent.agent_id == agent_id,
            InvestigationRouteEvent.work_date == work_date,
        ).distinct().all()
    ]
    by_case = route_attempt_history(db, event_case_ids)
    return [attempt for attempts in by_case.values() for attempt in attempts]
