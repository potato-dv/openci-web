from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.agent_revisit import AgentRevisitRequest
from app.models.investigation import Investigation
from app.models.report import InvestigationReport
from app.models.planning import AgentShift
from app.models.user import User
from app.services.agent_schedules import (
    MANILA,
    availability_preview,
    enqueue_planning_trigger,
    materialize_work_date,
)


ACTIVE_REVISIT_STATUSES = ("waiting_for_shift", "queued", "routed")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _next_available_shift(db: Session, agent_id: int, from_date: date, now: datetime) -> dict | None:
    agent = db.query(User).filter(User.id == agent_id, User.role == "agent").first()
    if agent is None or not agent.is_active:
        return None
    to_date = from_date + timedelta(days=30)
    preview = availability_preview(db, agent_id, from_date, to_date)
    for day in preview["days"]:
        if not day.get("is_available") or day.get("shift_ends_at") is None:
            continue
        if _utc(day["shift_ends_at"]) <= now:
            continue
        if day.get("start_latitude") is None or day.get("start_longitude") is None:
            continue
        return day
    return None


def _shift_bounds(day: dict) -> tuple[datetime, datetime]:
    return _utc(day["shift_starts_at"]), _utc(day["shift_ends_at"])


def get_agent_revisit_request(
    db: Session,
    investigation_id: int,
    agent_id: int,
) -> AgentRevisitRequest | None:
    return (
        db.query(AgentRevisitRequest)
        .filter(
            AgentRevisitRequest.investigation_id == investigation_id,
            AgentRevisitRequest.agent_id == agent_id,
        )
        .order_by(AgentRevisitRequest.created_at.desc(), AgentRevisitRequest.id.desc())
        .first()
    )


def can_request_agent_revisit(
    db: Session,
    investigation: Investigation,
    agent: User,
) -> bool:
    if (
        agent.role != "agent"
        or not agent.is_active
        or investigation.assigned_agent_id != agent.id
        or not investigation.location_confirmed
        or not investigation.region_code
        or investigation.status not in {"returned_for_correction", "in_progress"}
    ):
        return False
    latest_report = (
        db.query(InvestigationReport)
        .filter(InvestigationReport.investigation_id == investigation.id)
        .order_by(InvestigationReport.version.desc(), InvestigationReport.id.desc())
        .first()
    )
    returned_report = (
        db.query(InvestigationReport)
        .filter(
            InvestigationReport.investigation_id == investigation.id,
            InvestigationReport.status == "returned_for_correction",
        )
        .order_by(InvestigationReport.version.desc(), InvestigationReport.id.desc())
        .first()
    )
    if returned_report is None or latest_report is None:
        return False
    if latest_report.status not in {"returned_for_correction", "draft"}:
        return False
    active_request = db.query(AgentRevisitRequest.id).filter(
        AgentRevisitRequest.report_id == returned_report.id,
        AgentRevisitRequest.status.in_(ACTIVE_REVISIT_STATUSES),
    ).first()
    return active_request is None


def request_agent_revisit(
    db: Session,
    investigation: Investigation,
    agent: User,
    now: datetime | None = None,
) -> AgentRevisitRequest:
    now = _utc(now or datetime.now(timezone.utc))
    locked_case = (
        db.query(Investigation)
        .filter(Investigation.id == investigation.id)
        .with_for_update()
        .first()
    )
    if locked_case is None or locked_case.deleted_at is not None:
        raise ValueError("investigation_not_found")
    if locked_case.assigned_agent_id != agent.id:
        raise ValueError("agent_assignment_changed")
    if not locked_case.location_confirmed or not locked_case.region_code:
        raise ValueError("confirmed_location_required")

    latest_report = (
        db.query(InvestigationReport)
        .filter(InvestigationReport.investigation_id == locked_case.id)
        .order_by(InvestigationReport.version.desc(), InvestigationReport.id.desc())
        .first()
    )
    returned_report = (
        db.query(InvestigationReport)
        .filter(
            InvestigationReport.investigation_id == locked_case.id,
            InvestigationReport.status == "returned_for_correction",
        )
        .order_by(InvestigationReport.version.desc(), InvestigationReport.id.desc())
        .first()
    )
    if returned_report is None:
        raise ValueError("returned_report_required")

    if latest_report is None or latest_report.status not in {"returned_for_correction", "draft"}:
        raise ValueError("returned_report_required")

    existing = db.query(AgentRevisitRequest).filter(
        AgentRevisitRequest.report_id == returned_report.id,
    ).with_for_update().first()
    if existing is not None and existing.status in ACTIVE_REVISIT_STATUSES:
        return existing

    if locked_case.status not in {"returned_for_correction", "in_progress"}:
        raise ValueError("returned_report_required")

    today = now.astimezone(MANILA).date()
    materialize_work_date(db, today)
    shift_day = _next_available_shift(db, agent.id, today, now)
    request = existing or AgentRevisitRequest(
        investigation_id=locked_case.id,
        report_id=returned_report.id,
        agent_id=agent.id,
    )
    request.target_work_date = shift_day["work_date"] if shift_day else None
    request.status = "waiting_for_shift"
    request.planning_run_id = None
    request.completed_at = None
    db.add(request)
    db.flush()

    if shift_day is not None and shift_day["work_date"] == today and _shift_bounds(shift_day)[0] <= now:
        request.status = "queued"
        locked_case.status = "assigned"
        enqueue_planning_trigger(db, today, shift_day["region_code"], "agent_revisit_requested")
    db.flush()
    return request


def activate_due_revisit_requests(
    db: Session,
    work_date: date,
    now: datetime | None = None,
) -> int:
    """Activate persistent revisit requests only when the target workday starts."""
    now = _utc(now or datetime.now(timezone.utc))
    requests = (
        db.query(AgentRevisitRequest)
        .filter(
            AgentRevisitRequest.status.in_(("waiting_for_shift", "queued")),
            (AgentRevisitRequest.target_work_date.is_(None))
            | (AgentRevisitRequest.target_work_date <= work_date),
        )
        .order_by(AgentRevisitRequest.created_at, AgentRevisitRequest.id)
        .with_for_update(skip_locked=True)
        .all()
    )
    activated = 0
    for request in requests:
        case = db.query(Investigation).filter(
            Investigation.id == request.investigation_id,
        ).with_for_update().first()
        if case is None or case.deleted_at is not None or case.assigned_agent_id != request.agent_id:
            request.status = "cancelled"
            continue
        if case.status in {"completed", "under_review"}:
            request.status = "completed"
            request.completed_at = now
            continue
        if request.status == "queued" and request.target_work_date == work_date:
            current_shift = db.query(AgentShift).filter(
                AgentShift.agent_id == request.agent_id,
                AgentShift.work_date == work_date,
            ).with_for_update().first()
            if current_shift and current_shift.is_available:
                shift_start = _utc(current_shift.shift_starts_at)
                shift_end = _utc(current_shift.shift_ends_at)
                if shift_start <= now < shift_end:
                    continue
                if now < shift_start:
                    request.status = "waiting_for_shift"
                    continue
            request.status = "waiting_for_shift"
            request.target_work_date = None

        from_date = max(work_date, request.target_work_date or work_date)
        shift_day = _next_available_shift(db, request.agent_id, from_date, now)
        if shift_day is None:
            request.target_work_date = None
            request.status = "waiting_for_shift"
            if case.status == "assigned":
                case.status = "returned_for_correction"
            continue

        request.target_work_date = shift_day["work_date"]
        if shift_day["work_date"] != work_date:
            request.status = "waiting_for_shift"
            if case.status == "assigned":
                case.status = "returned_for_correction"
            continue

        shift = db.query(AgentShift).filter(
            AgentShift.agent_id == request.agent_id,
            AgentShift.work_date == work_date,
        ).with_for_update().first()
        if (
            shift is None
            or not shift.is_available
            or not (_utc(shift.shift_starts_at) <= now < _utc(shift.shift_ends_at))
        ):
            if shift is not None and shift.is_available and now < _utc(shift.shift_starts_at):
                request.status = "waiting_for_shift"
                continue
            request.target_work_date = None
            request.status = "waiting_for_shift"
            if case.status == "assigned":
                case.status = "returned_for_correction"
            continue

        case.status = "assigned"
        request.status = "queued"
        enqueue_planning_trigger(db, work_date, shift.region_code, "agent_revisit_shift_started")
        activated += 1
    db.flush()
    return activated


def complete_agent_revisit_requests(
    db: Session,
    investigation_id: int,
    submitted_report_id: int,
    submitted_at: datetime,
) -> int:
    completed = 0
    requests = db.query(AgentRevisitRequest).filter(
        AgentRevisitRequest.investigation_id == investigation_id,
        AgentRevisitRequest.status.in_(ACTIVE_REVISIT_STATUSES),
        AgentRevisitRequest.report_id != submitted_report_id,
    ).with_for_update().all()
    for request in requests:
        if _utc(submitted_at) >= _utc(request.created_at):
            request.status = "completed"
            request.completed_at = _utc(submitted_at)
            completed += 1
    return completed
