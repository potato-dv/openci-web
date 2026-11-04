"""End shifts, retry missed visits, and preserve work already in progress."""

from datetime import date, datetime, timedelta, timezone
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.activity import ActivityLog
from app.models.assignment import InvestigationAssignment
from app.models.investigation import Investigation
from app.models.planning import AgentShift, PlanningItem, PlanningRoute, PlanningRun
from app.models.report import InvestigationReport
from app.models.route_event import InvestigationRouteEvent
from app.services.agent_schedules import (
    ALL_REGIONS,
    MANILA,
    enqueue_planning_trigger,
    reconcile_prematurely_ended_recurring_shifts,
)
from app.services.route_workflow import next_valid_work_date


ACTIVE_RUN_STATUSES = ("queued", "running", "ready")
RETRYABLE_STATUSES = ("pending", "assigned")
CLOCK_SKEW_TOLERANCE_SECONDS = 120
logger = logging.getLogger("app.shift_expiry")


def _utc(value: datetime) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _queue_case_retry(
    db: Session,
    case: Investigation,
    work_date: date,
    reason: str,
    queued_scopes: set[tuple[date, str]],
) -> None:
    scope = case.region_code or ALL_REGIONS
    enqueue_planning_trigger(db, work_date, case.region_code, reason)
    queued_scopes.add((work_date, scope))


def _restore_published_route(
    db: Session,
    shift: AgentShift,
    case: Investigation,
) -> int | None:
    """Reconnect an applied route cleared by a future-dated shift expiry."""
    if shift.current_planning_run_id is not None:
        return shift.current_planning_run_id
    run = (
        db.query(PlanningRun)
        .join(PlanningItem, PlanningItem.planning_run_id == PlanningRun.id)
        .join(
            PlanningRoute,
            (PlanningRoute.planning_run_id == PlanningRun.id)
            & (PlanningRoute.agent_id == shift.agent_id),
        )
        .filter(
            PlanningRun.work_date == shift.work_date,
            PlanningRun.status == "applied",
            PlanningRun.auto_publish.is_(True),
            PlanningItem.investigation_id == case.id,
            PlanningItem.agent_id == shift.agent_id,
            PlanningItem.outcome == "assigned",
            PlanningRoute.geometry_status == "ready",
        )
        .order_by(PlanningRun.id.desc())
        .first()
    )
    if run is None:
        return None
    shift.current_planning_run_id = run.id
    return run.id


def process_shift_end_investigations(
    db: Session,
    now: datetime | None = None,
) -> dict[str, int]:
    """End shifts and record unvisited work without changing investigation lifecycle.

    Manual assignments remain with their agent and queue for that agent's next
    valid working shift. Automatic assignments return to the planning pool.
    Work already started, a submitted report, and supervisor review are kept.
    """
    now_utc = _utc(now or datetime.now(timezone.utc))
    if now is None:
        database_now = db.execute(text("SELECT CURRENT_TIMESTAMP")).scalar_one()
        database_now_utc = _utc(database_now)
        skew_seconds = abs((now_utc - database_now_utc).total_seconds())
        if skew_seconds > CLOCK_SKEW_TOLERANCE_SECONDS:
            logger.warning(
                "shift_end_clock_skew_detected app_now=%s database_now=%s skew_seconds=%.1f",
                now_utc.isoformat(),
                database_now_utc.isoformat(),
                skew_seconds,
            )
            db.rollback()
            return {
                "ended_shifts": 0,
                "reconciled_shifts": 0,
                "cancelled": 0,
                "carried_over": 0,
                "reopened": 0,
                "restored_future_cancellations": 0,
                "stale_runs": 0,
                "planning_triggers": 0,
            }
    today = now_utc.astimezone(MANILA).date()

    future_events = (
        db.query(ActivityLog)
        .filter(
            ActivityLog.action == "investigation.cancelled_at_shift_end",
            ActivityLog.object_type == "investigation",
            ActivityLog.created_at
            > now_utc + timedelta(seconds=CLOCK_SKEW_TOLERANCE_SECONDS),
        )
        .order_by(ActivityLog.created_at, ActivityLog.id)
        .all()
    )
    future_events = [
        event for event in future_events
        if (event.details or {}).get("work_date") == today.isoformat()
    ]
    event_case_ids = {event.object_id for event in future_events if event.object_id is not None}

    due_shift_snapshots = db.query(AgentShift.id, AgentShift.agent_id).filter(
        AgentShift.is_available.is_(True),
        AgentShift.work_date <= today,
        AgentShift.shift_ends_at <= now_utc,
    ).all()
    due_shift_ids = {shift_id for shift_id, _agent_id in due_shift_snapshots}
    due_agent_ids = {agent_id for _shift_id, agent_id in due_shift_snapshots}
    missed_visit_case_ids = set()
    if due_agent_ids:
        missed_visit_case_ids = {
            case_id for (case_id,) in db.query(Investigation.id).filter(
                Investigation.assigned_agent_id.in_(due_agent_ids),
                Investigation.deleted_at.is_(None),
                Investigation.status.in_(RETRYABLE_STATUSES),
            ).all()
        }
    due_reopen_case_ids = {
        case_id for (case_id,) in db.query(Investigation.id).filter(
            Investigation.deleted_at.is_(None),
            Investigation.status == "cancelled",
            Investigation.reopen_on <= today,
        ).all()
    }

    candidate_case_ids = sorted(
        event_case_ids | missed_visit_case_ids | due_reopen_case_ids
    )
    cases = (
        db.query(Investigation)
        .filter(Investigation.id.in_(candidate_case_ids))
        .order_by(Investigation.id)
        .with_for_update()
        .populate_existing()
        .all()
    ) if candidate_case_ids else []
    cases_by_id = {case.id: case for case in cases}

    active_assignments = (
        db.query(InvestigationAssignment)
        .filter(
            InvestigationAssignment.investigation_id.in_(candidate_case_ids),
            InvestigationAssignment.is_active.is_(True),
        )
        .order_by(InvestigationAssignment.id)
        .with_for_update()
        .all()
    ) if candidate_case_ids else []
    assignment_by_case = {
        assignment.investigation_id: assignment for assignment in active_assignments
    }

    # Lock investigation rows before shifts. This matches route publication's
    # entity-first lock order and avoids a shift/case deadlock on retries.
    reconciled = reconcile_prematurely_ended_recurring_shifts(db, now_utc)

    referenced_shift_ids = {
        int((event.details or {}).get("shift_id"))
        for event in future_events
        if (event.details or {}).get("shift_id") is not None
    }
    locked_shift_ids = sorted(due_shift_ids | referenced_shift_ids)
    locked_shifts = (
        db.query(AgentShift)
        .filter(AgentShift.id.in_(locked_shift_ids))
        .order_by(AgentShift.agent_id, AgentShift.id)
        .with_for_update()
        .all()
    ) if locked_shift_ids else []
    shifts_by_id = {shift.id: shift for shift in locked_shifts}

    visited_case_ids = set()
    if candidate_case_ids:
        visited_case_ids = {
            case_id for (case_id,) in db.query(InvestigationReport.investigation_id)
            .filter(
                InvestigationReport.investigation_id.in_(candidate_case_ids),
                InvestigationReport.visit_outcome.is_not(None),
            )
            .distinct()
            .all()
        }

    queued_scopes: set[tuple[date, str]] = set()
    restored_future_cancellations = 0
    for event in future_events:
        case = cases_by_id.get(event.object_id)
        details = event.details or {}
        try:
            shift_id = int(details.get("shift_id"))
        except (TypeError, ValueError):
            continue
        shift = shifts_by_id.get(shift_id)
        previous_status = details.get("previous_status")
        if (
            case is None
            or shift is None
            or previous_status not in RETRYABLE_STATUSES
            or case.status != "cancelled"
            or case.reopen_on != shift.work_date + timedelta(days=1)
            or case.assigned_agent_id != shift.agent_id
            or case.id in visited_case_ids
            or shift.work_date != today
            or shift.source != "recurring"
            or not shift.is_available
            or _utc(shift.shift_starts_at) > now_utc
            or _utc(shift.shift_ends_at) <= now_utc
            or _utc(event.created_at)
            <= now_utc + timedelta(seconds=CLOCK_SKEW_TOLERANCE_SECONDS)
        ):
            continue

        case.status = previous_status
        case.reopen_on = None
        restored_run_id = _restore_published_route(db, shift, case)
        restored_future_cancellations += 1
        db.add(ActivityLog(
            actor_id=None,
            action="investigation.restored_after_future_shift_end",
            object_type="investigation",
            object_id=case.id,
            details={
                "shift_id": shift.id,
                "work_date": today.isoformat(),
                "restored_status": previous_status,
                "cancellation_event_id": event.id,
                "cancellation_recorded_at": _utc(event.created_at).isoformat(),
                "observed_at": now_utc.isoformat(),
                "restored_planning_run_id": restored_run_id,
            },
        ))
        if restored_run_id is None:
            _queue_case_retry(
                db,
                case,
                today,
                "future_shift_end_cancellation_reconciled",
                queued_scopes,
            )

    ended_agent_date_pairs: set[tuple[int, date]] = set()
    cancelled = 0
    carried_over = 0
    due_shifts = (
        db.query(AgentShift)
        .filter(
            AgentShift.is_available.is_(True),
            AgentShift.work_date <= today,
            AgentShift.shift_ends_at <= now_utc,
        )
        .order_by(AgentShift.agent_id, AgentShift.id)
        .with_for_update()
        .all()
    )
    for shift in due_shifts:
        if not shift.is_available or _utc(shift.shift_ends_at) > now_utc:
            continue
        shift.is_available = False
        ended_agent_date_pairs.add((shift.agent_id, shift.work_date))
        db.add(ActivityLog(
            actor_id=None,
            action="agent_shift.ended",
            object_type="agent_shift",
            object_id=shift.id,
            details={
                "work_date": shift.work_date.isoformat(),
                "shift_ends_at": _utc(shift.shift_ends_at).isoformat(),
                "observed_at": now_utc.isoformat(),
            },
        ))

        for case in cases:
            if (
                case.deleted_at is not None
                or case.assigned_agent_id != shift.agent_id
                or case.status not in RETRYABLE_STATUSES
                or case.id in visited_case_ids
            ):
                continue
            assignment = assignment_by_case.get(case.id)
            assignment_at = assignment.assigned_at if assignment is not None else case.created_at
            if assignment_at is not None and _utc(assignment_at) > _utc(shift.shift_ends_at):
                # A delayed expiry tick must not carry an assignment that was
                # made after this older shift had already ended.
                continue
            prior_events = db.query(InvestigationRouteEvent).filter(
                InvestigationRouteEvent.investigation_id == case.id,
                InvestigationRouteEvent.agent_id == shift.agent_id,
                InvestigationRouteEvent.work_date == shift.work_date,
            ).order_by(InvestigationRouteEvent.attempted_at.desc(), InvestigationRouteEvent.id.desc()).all()
            if any(event.event_type == "shift_end_not_visited" for event in prior_events):
                continue
            assignment_source = assignment.assignment_source if assignment else None
            if assignment_source == "manual":
                next_work_date = next_valid_work_date(db, shift.agent_id, shift.work_date)
            else:
                next_work_date = max(today, shift.work_date + timedelta(days=1))
            no_contact_events = [event for event in prior_events if event.event_type == "no_contact"]
            no_contact_event = no_contact_events[0] if no_contact_events else None
            if no_contact_event is None:
                db.add(InvestigationRouteEvent(
                    investigation_id=case.id,
                    agent_id=shift.agent_id,
                    work_date=shift.work_date,
                    planning_run_id=shift.current_planning_run_id,
                    event_type="shift_end_not_visited",
                    state="carried_over",
                    retry_number=0,
                    reason="shift_end_not_visited",
                    notes=None,
                    attempted_at=now_utc,
                    next_work_date=next_work_date,
                    latitude=case.latitude,
                    longitude=case.longitude,
                    finalized_at=now_utc,
                ))
                carried_over += 1
            else:
                # The no-contact attempt is the carry-over record. Finalize
                # it in place and keep retries attached to the same work item.
                for attempt in no_contact_events:
                    if attempt.state in {"deferred", "retrying", "retry_failed"}:
                        attempt.state = "carried_over"
                        attempt.finalized_at = now_utc
                    attempt.next_work_date = next_work_date
                carried_over += 1

            if assignment is not None and assignment.assignment_source == "automatic":
                assignment.is_active = False
                assignment.unassigned_at = now_utc
                assignment.auto_route_status = None
                assignment.auto_route_work_date = None
                assignment.auto_route_run_ids = None
                assignment.auto_route_agent_ids = None
                assignment.auto_route_errors = None
                case.assigned_agent_id = None
                case.status = "pending"
                case.reopen_on = None

            db.add(ActivityLog(
                actor_id=None,
                action="investigation.carried_over_at_shift_end",
                object_type="investigation",
                object_id=case.id,
                details={
                    "shift_id": shift.id,
                    "work_date": shift.work_date.isoformat(),
                    "assignment_source": assignment_source,
                    "previous_agent_id": shift.agent_id,
                    "assigned_agent_id": case.assigned_agent_id,
                    "next_work_date": next_work_date.isoformat() if next_work_date else None,
                    "observed_at": now_utc.isoformat(),
                    "reason": "shift_end_not_visited" if no_contact_event is None else "no_contact_attempt_carried_over",
                },
            ))
            if next_work_date is not None:
                _queue_case_retry(
                    db,
                    case,
                    next_work_date,
                    "investigation_carried_over_at_shift_end",
                    queued_scopes,
                )

    active_runs = (
        db.query(PlanningRun)
        .filter(
            PlanningRun.work_date.in_({work_date for _agent_id, work_date in ended_agent_date_pairs}),
            PlanningRun.status.in_(ACTIVE_RUN_STATUSES),
        )
        .order_by(PlanningRun.id)
        .with_for_update()
        .all()
    ) if ended_agent_date_pairs else []

    stale_runs = 0
    for run in active_runs:
        if any(
            work_date == run.work_date and agent_id in (run.agent_ids or [])
            for agent_id, work_date in ended_agent_date_pairs
        ):
            run.status = "stale"
            run.error_code = "shift_ended"
            run.finished_at = now_utc
            stale_runs += 1
            for shift in due_shifts:
                if shift.work_date == run.work_date and shift.agent_id in (run.agent_ids or []) and shift.current_planning_run_id == run.id:
                    shift.current_planning_run_id = None

    reopened = 0
    for case in cases:
        if (
            case.status != "cancelled"
            or case.reopen_on is None
            or case.reopen_on > today
            or case.deleted_at is not None
        ):
            continue
        previous_reopen_on = case.reopen_on
        previous_agent_id = case.assigned_agent_id
        assignment = assignment_by_case.get(case.id)
        assignment_source = assignment.assignment_source if assignment else None
        if assignment and assignment.assignment_source == "automatic":
            assignment.is_active = False
            assignment.unassigned_at = now_utc
            assignment.auto_route_status = None
            assignment.auto_route_work_date = None
            assignment.auto_route_run_ids = None
            assignment.auto_route_agent_ids = None
            assignment.auto_route_errors = None
            case.assigned_agent_id = None
        elif assignment:
            # Manual work keeps its owner; only its previous-day route attempt
            # is cleared so today's planner can publish a fresh route.
            assignment.auto_route_status = None
            assignment.auto_route_work_date = None
            assignment.auto_route_run_ids = None
            assignment.auto_route_agent_ids = None
            assignment.auto_route_errors = None

        case.status = "pending"
        case.reopen_on = None
        reopened += 1
        db.add(ActivityLog(
            actor_id=None,
            action="investigation.reopened_after_shift",
            object_type="investigation",
            object_id=case.id,
            details={
                "previous_reopen_on": previous_reopen_on.isoformat(),
                "assignment_source": assignment_source,
                "previous_assigned_agent_id": previous_agent_id,
                "assigned_agent_id": case.assigned_agent_id,
                "work_date": today.isoformat(),
            },
        ))
        _queue_case_retry(
            db,
            case,
            today,
            "investigation_reopened_after_shift",
            queued_scopes,
        )

    db.commit()
    return {
        "ended_shifts": len(ended_agent_date_pairs),
        "reconciled_shifts": reconciled,
        "cancelled": cancelled,
        "carried_over": carried_over,
        "reopened": reopened,
        "restored_future_cancellations": restored_future_cancellations,
        "stale_runs": stale_runs,
        "planning_triggers": len(queued_scopes),
    }
