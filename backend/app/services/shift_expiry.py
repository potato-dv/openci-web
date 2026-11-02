"""Durable shift-end cancellation and next-Manila-day reopening."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.activity import ActivityLog
from app.models.assignment import InvestigationAssignment
from app.models.investigation import Investigation
from app.models.planning import AgentShift, PlanningRun
from app.models.user import User
from app.services.agent_schedules import ALL_REGIONS, MANILA, enqueue_planning_trigger


UNFINISHED_STATUSES = ("pending", "assigned", "in_progress")
ACTIVE_RUN_STATUSES = ("queued", "running", "ready")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def process_shift_end_investigations(
    db: Session,
    now: datetime | None = None,
) -> dict[str, int]:
    """Cancel expired-shift work and reopen due cases, safely on every retry.

    Cases are locked in ID order before shifts and planning runs, matching the
    publication path's entity-first lock order. The persisted ``reopen_on``
    date is the source of truth if a worker is stopped across midnight.
    """
    now_utc = _utc(now or datetime.now(timezone.utc))
    today = now_utc.astimezone(MANILA).date()

    due_shifts = (
        db.query(AgentShift)
        .filter(AgentShift.is_available.is_(True), AgentShift.work_date <= today)
        .order_by(AgentShift.agent_id, AgentShift.id)
        .all()
    )
    due_shifts = [shift for shift in due_shifts if _utc(shift.shift_ends_at) <= now_utc]
    expired_shift_ids = {shift.id for shift in due_shifts}
    expired_agent_ids = {shift.agent_id for shift in due_shifts}

    candidate_case_ids: set[int] = set()
    if expired_agent_ids:
        candidate_case_ids.update(
            investigation_id
            for (investigation_id,) in db.query(Investigation.id)
            .filter(
                Investigation.assigned_agent_id.in_(expired_agent_ids),
                Investigation.deleted_at.is_(None),
                Investigation.status.in_(UNFINISHED_STATUSES),
            )
            .all()
        )
    candidate_case_ids.update(
        investigation_id
        for (investigation_id,) in db.query(Investigation.id)
        .filter(
            Investigation.deleted_at.is_(None),
            Investigation.status == "cancelled",
            Investigation.reopen_on <= today,
        )
        .all()
    )

    cases = (
        db.query(Investigation)
        .filter(Investigation.id.in_(sorted(candidate_case_ids)))
        .order_by(Investigation.id)
        .with_for_update()
        .populate_existing()
        .all()
    ) if candidate_case_ids else []

    # Re-read and lock shifts only after cases to keep lock order consistent
    # with apply_run. Old due snapshots are consumed together so a missed
    # midnight task cannot leave a prior day's availability active forever.
    shifts_by_id = {
        shift.id: shift
        for shift in (
            db.query(AgentShift)
            .filter(AgentShift.id.in_(sorted(expired_shift_ids)))
            .order_by(AgentShift.agent_id, AgentShift.id)
            .with_for_update()
            .populate_existing()
            .all()
        )
    } if expired_shift_ids else {}
    cases_by_id = {case.id: case for case in cases}
    active_assignments_by_case = {
        assignment.investigation_id: assignment
        for assignment in db.query(InvestigationAssignment).filter(
            InvestigationAssignment.investigation_id.in_(sorted(candidate_case_ids)),
            InvestigationAssignment.is_active.is_(True),
        ).all()
    } if candidate_case_ids else {}

    still_due_shifts = [
        shift for shift in shifts_by_id.values()
        if shift.is_available and _utc(shift.shift_ends_at) <= now_utc
    ]
    expired_shifts_by_agent: dict[int, list[AgentShift]] = {}
    for shift in still_due_shifts:
        expired_shifts_by_agent.setdefault(shift.agent_id, []).append(shift)
    for shifts in expired_shifts_by_agent.values():
        shifts.sort(key=lambda shift: (shift.work_date, shift.id))

    # Consume every ended snapshot. Each case is associated with the shift it
    # was assigned for, so a delayed worker still uses that shift's next-day
    # reopen date. An assignment created after an older shift belongs to a
    # newer shift and is left alone.
    ended_agent_date_pairs: set[tuple[int, date]] = set()
    for shift in still_due_shifts:
        shift.is_available = False
        shift.current_planning_run_id = None
        ended_agent_date_pairs.add((shift.agent_id, shift.work_date))

    case_shift_by_id: dict[int, AgentShift] = {}
    for case in cases:
        if (
            case.assigned_agent_id is None
            or case.status not in UNFINISHED_STATUSES
            or case.deleted_at is not None
        ):
            continue
        agent_shifts = expired_shifts_by_agent.get(case.assigned_agent_id, [])
        if not agent_shifts:
            continue

        assignment = active_assignments_by_case.get(case.id)
        if assignment is None:
            # Legacy assigned cases without an assignment row are associated
            # with the latest known shift, matching the previous fallback.
            case_shift_by_id[case.id] = agent_shifts[-1]
            continue

        assigned_work_date = (
            assignment.auto_route_work_date
            or _utc(assignment.assigned_at).astimezone(MANILA).date()
        )
        if assigned_work_date > agent_shifts[-1].work_date:
            # A newer assignment cannot be cancelled by an older expired
            # shift for the same agent.
            continue

        matching_shift = next(
            (shift for shift in agent_shifts if shift.work_date == assigned_work_date),
            None,
        )
        if matching_shift is None:
            # If several missed shifts are processed together, associate a
            # preassigned item with the first expired shift on or after its
            # assignment date. This preserves its actual next-day reopen date.
            matching_shift = next(
                (shift for shift in agent_shifts if shift.work_date > assigned_work_date),
                agent_shifts[-1],
            )
        case_shift_by_id[case.id] = matching_shift

    cancelled = 0
    stale_runs = 0
    cancelled_case_ids: set[int] = set()
    for case_id, shift in sorted(
        case_shift_by_id.items(),
        key=lambda row: (row[1].work_date, row[0]),
    ):
        case = cases_by_id[case_id]
        # The row may have changed after the initial candidate query; the
        # investigation lock makes this check authoritative.
        if case.status not in UNFINISHED_STATUSES or case.assigned_agent_id != shift.agent_id:
            continue
        previous_status = case.status
        reopen_on = shift.work_date + timedelta(days=1)
        case.status = "cancelled"
        case.reopen_on = reopen_on
        cancelled += 1
        cancelled_case_ids.add(case.id)
        db.add(ActivityLog(
            actor_id=None,
            action="investigation.cancelled_at_shift_end",
            object_type="investigation",
            object_id=case.id,
            details={
                "shift_id": shift.id,
                "work_date": shift.work_date.isoformat(),
                "previous_status": previous_status,
                "reopen_on": reopen_on.isoformat(),
            },
        ))

    active_runs = db.query(PlanningRun).filter(
        PlanningRun.work_date.in_({work_date for _agent_id, work_date in ended_agent_date_pairs}),
        PlanningRun.status.in_(ACTIVE_RUN_STATUSES),
    ).order_by(PlanningRun.id).with_for_update().all() if ended_agent_date_pairs else []
    for run in active_runs:
        stale_for_shift = any(
            work_date == run.work_date and agent_id in (run.agent_ids or [])
            for agent_id, work_date in ended_agent_date_pairs
        )
        stale_for_cancelled_case = bool(cancelled_case_ids.intersection(run.investigation_ids or []))
        if stale_for_shift or stale_for_cancelled_case:
            run.status = "stale"
            run.error_code = "shift_ended"
            run.finished_at = now_utc
            stale_runs += 1

    reopened = 0
    triggers_queued = 0
    for case in cases:
        if case.status != "cancelled" or case.reopen_on is None or case.reopen_on > today:
            continue
        previous_reopen_on = case.reopen_on
        previous_agent_id = case.assigned_agent_id
        active_assignment = None
        if previous_agent_id is not None:
            active_assignment = (
                db.query(InvestigationAssignment)
                .filter(
                    InvestigationAssignment.investigation_id == case.id,
                    InvestigationAssignment.agent_id == previous_agent_id,
                    InvestigationAssignment.is_active.is_(True),
                )
                .with_for_update()
                .first()
            )

        if active_assignment and active_assignment.assignment_source == "automatic":
            active_assignment.is_active = False
            active_assignment.unassigned_at = now_utc
            active_assignment.auto_route_status = None
            active_assignment.auto_route_run_ids = None
            active_assignment.auto_route_agent_ids = None
            case.assigned_agent_id = None
        elif active_assignment:
            active_assignment.auto_route_status = None
            active_assignment.auto_route_run_ids = None
            active_assignment.auto_route_agent_ids = None

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
                "assignment_source": active_assignment.assignment_source if active_assignment else None,
                "assigned_agent_id": case.assigned_agent_id,
            },
        ))

        manual_owner_id = (
            previous_agent_id
            if previous_agent_id is not None
            and (active_assignment is None or active_assignment.assignment_source == "manual")
            else None
        )
        available_shift_query = db.query(AgentShift.id).join(
            User, User.id == AgentShift.agent_id,
        ).filter(
            AgentShift.work_date == today,
            AgentShift.is_available.is_(True),
            User.role == "agent",
            User.is_active.is_(True),
            AgentShift.region_code.in_((case.region_code, ALL_REGIONS)) if case.region_code else AgentShift.region_code == ALL_REGIONS,
        )
        if manual_owner_id is not None:
            available_shift_query = available_shift_query.filter(AgentShift.agent_id == manual_owner_id)
        available_shift = available_shift_query.first()
        if case.region_code and available_shift:
            enqueue_planning_trigger(db, today, case.region_code, "investigation_reopened_after_shift")
            triggers_queued += 1

    db.commit()
    return {
        "cancelled": cancelled,
        "reopened": reopened,
        "stale_runs": stale_runs,
        "planning_triggers": triggers_queued,
    }
