from datetime import date, datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.assignment import InvestigationAssignment
from app.models.investigation import Investigation
from app.models.planning import AgentShift
from app.models.agent_revisit import AgentRevisitRequest
from app.models.report import InvestigationReport
from app.models.review import InvestigationReview
from app.models.activity import ActivityLog
from app.models.user import User
from app.schemas.investigation import InvestigationCreate, InvestigationUpdate


def _as_utc(value: datetime) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def create_investigation(
    db: Session,
    data: InvestigationCreate,
) -> Investigation:
    values = data.model_dump()
    investigation = Investigation(reference_number=f"INV-{uuid4().hex.upper()}", **values)

    db.add(investigation)
    db.commit()
    db.refresh(investigation)

    return investigation

def get_investigations(
    db: Session,
    current_user: User,
) -> list[Investigation]:
    query = db.query(Investigation)
    query = query.filter(Investigation.deleted_at.is_(None))

    if current_user.role == "agent":
        query = query.filter(Investigation.assigned_agent_id == current_user.id)

    return query.order_by(Investigation.created_at.desc()).all()


def get_trashed_investigations(db: Session) -> list[Investigation]:
    return (
        db.query(Investigation)
        .filter(Investigation.deleted_at.is_not(None))
        .order_by(Investigation.deleted_at.desc())
        .all()
    )


def get_trashed_investigation(
    db: Session,
    investigation_id: int,
) -> Investigation | None:
    return (
        db.query(Investigation)
        .filter(
            Investigation.id == investigation_id,
            Investigation.deleted_at.is_not(None),
        )
        .first()
    )


def restore_investigation(
    db: Session,
    investigation: Investigation,
    actor: User,
) -> Investigation:
    investigation.deleted_at = None
    db.add(ActivityLog(
        actor_id=actor.id,
        action="investigation.restored",
        object_type="investigation",
        object_id=investigation.id,
        details={"reference_number": investigation.reference_number},
    ))
    db.commit()
    db.refresh(investigation)
    return investigation

def get_investigation(
    db: Session,
    investigation_id: int,
) -> Investigation | None:
    return (
        db.query(Investigation)
        .filter(Investigation.id == investigation_id, Investigation.deleted_at.is_(None))
        .first()
    )

def update_investigation(
    db: Session,
    investigation: Investigation,
    data: InvestigationUpdate,
) -> Investigation:
    investigation = (
        db.query(Investigation)
        .filter(Investigation.id == investigation.id)
        .with_for_update()
        .one()
    )
    route_agent_id = investigation.assigned_agent_id
    original_region_code = investigation.region_code
    update_data = data.model_dump(exclude_unset=True)

    address_fields = {
        "legacy_address", "house_number", "unit_floor_building_name", "street",
        "subdivision_village_purok", "region_code", "province_code",
        "city_municipality_code", "barangay_code", "postal_code",
    }
    if address_fields.intersection(update_data):
        investigation.latitude = None
        investigation.longitude = None
        investigation.location_source = None
        investigation.location_provider_ref = None
        investigation.location_confirmed_at = None
        investigation.location_confirmed_by_id = None
        investigation.h3_r7 = None
        investigation.h3_r8 = None
        investigation.h3_r9 = None

    if {"first_name", "middle_name", "last_name"}.issubset(update_data):
        investigation.legacy_subject_name = None

    for field, value in update_data.items():
        setattr(investigation, field, value)

    not_before = investigation.visit_not_before_at
    due = investigation.visit_due_at
    if not_before and due:
        if not_before.tzinfo is None:
            not_before = not_before.replace(tzinfo=timezone.utc)
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        if due <= not_before:
            raise ValueError("Visit due time must be after the earliest visit time")
    if investigation.service_duration_seconds < 300 or investigation.service_duration_seconds > 28800:
        raise ValueError("Service duration must be between 5 minutes and 8 hours")

    planning_fields = address_fields | {
        "priority", "service_duration_seconds", "visit_not_before_at", "visit_due_at",
    }
    if planning_fields.intersection(update_data):
        from app.models.planning import PlanningItem, PlanningRun

        affected_runs = select(PlanningItem.planning_run_id).where(
            PlanningItem.investigation_id == investigation.id
        )
        published_run_ids = select(PlanningItem.planning_run_id).where(
            PlanningItem.investigation_id == investigation.id,
        )
        from app.services.planning import clear_published_routes, planned_agent_ids_for_investigation

        clear_published_routes(
            db,
            published_run_ids,
            sorted(set(planned_agent_ids_for_investigation(db, investigation.id)) | ({route_agent_id} if route_agent_id is not None else set())),
        )
        db.query(PlanningRun).filter(
            PlanningRun.id.in_(affected_runs), PlanningRun.status.in_(("queued", "running", "ready"))
        ).update(
            {PlanningRun.status: "stale", PlanningRun.error_code: "investigation_changed"},
            synchronize_session=False,
        )
        from app.services.agent_schedules import enqueue_planning_trigger

        today = datetime.now(ZoneInfo("Asia/Manila")).date()
        for region in {value for value in (original_region_code, investigation.region_code) if value}:
            enqueue_planning_trigger(db, today, region, "investigation_planning_fields_changed")

    db.commit()
    db.refresh(investigation)

    return investigation


def can_access_investigation(
    investigation: Investigation,
    current_user: User,
) -> bool:
    return current_user.role in {"admin", "supervisor"} or (
        current_user.role == "agent"
        and investigation.assigned_agent_id == current_user.id
    )


def is_valid_status_transition(
    current_status: str,
    next_status: str,
) -> bool:
    allowed_transitions = {
        "pending": {"assigned", "cancelled"},
        "assigned": {"in_progress", "cancelled"},
        "in_progress": {"under_review", "cancelled"},
        "under_review": {"completed", "returned_for_correction"},
        "returned_for_correction": {"in_progress"},
        "cancelled": {"pending"},
        "completed": set(),
    }

    return next_status in allowed_transitions.get(current_status, set())


def get_assignment_history(
    db: Session,
    investigation_id: int,
) -> list[InvestigationAssignment]:
    return (
        db.query(InvestigationAssignment)
        .filter(InvestigationAssignment.investigation_id == investigation_id)
        .order_by(InvestigationAssignment.assigned_at.desc())
        .all()
    )


def assign_investigation(
    db: Session,
    investigation: Investigation,
    agent: User,
    assigned_by: User,
    note: str | None,
    commit: bool = True,
) -> InvestigationAssignment:
    if assigned_by.role not in {"admin", "supervisor"}:
        raise ValueError("Only administrators and supervisors can override assignments")
    if investigation.status not in {"pending", "assigned"}:
        raise ValueError("Only pending or assigned investigations can be assigned")
    investigation = (
        db.query(Investigation)
        .filter(Investigation.id == investigation.id)
        .with_for_update()
        .one()
    )
    if investigation.status not in {"pending", "assigned"}:
        raise ValueError("Only pending or assigned investigations can be assigned")

    candidate_agent = db.query(User).filter(User.id == agent.id).first()
    if candidate_agent is None or candidate_agent.role != "agent":
        raise ValueError("Investigation can only be assigned to an agent")
    if not candidate_agent.is_active:
        raise ValueError("Inactive agents cannot receive investigations")

    from app.models.planning import PlanningItem, PlanningRun

    agent = db.query(User).filter(User.id == agent.id).with_for_update().one()
    if not agent.is_active or agent.role != "agent":
        raise ValueError("Inactive or ineligible agents cannot receive investigations")
    if not investigation.location_confirmed:
        raise ValueError("Confirm the investigation location before assigning an agent")

    database_now = _as_utc(db.execute(text("SELECT CURRENT_TIMESTAMP")).scalar_one())
    work_date = database_now.astimezone(ZoneInfo("Asia/Manila")).date()
    shift = db.query(AgentShift).filter(
        AgentShift.agent_id == agent.id,
        AgentShift.work_date == work_date,
    ).with_for_update().first()
    if shift is None or not shift.is_available:
        raise ValueError("The agent has no available shift today")
    if database_now >= _as_utc(shift.shift_ends_at):
        raise ValueError("The agent's shift has ended; no new investigations can be assigned")
    if shift.region_code not in {investigation.region_code, "ALL"}:
        raise ValueError("The agent shift must match the investigation region")

    affected_runs = select(PlanningItem.planning_run_id).where(
        PlanningItem.investigation_id == investigation.id,
    )
    active_assignment = (
        db.query(InvestigationAssignment)
        .filter(
            InvestigationAssignment.investigation_id == investigation.id,
            InvestigationAssignment.is_active.is_(True),
        )
        .first()
    )

    if not (active_assignment and active_assignment.agent_id == agent.id):
        open_count = int(db.query(func.count(Investigation.id)).filter(
            Investigation.assigned_agent_id == agent.id,
            Investigation.id != investigation.id,
            Investigation.deleted_at.is_(None),
            Investigation.status.in_(("assigned", "in_progress", "under_review", "returned_for_correction")),
        ).scalar() or 0)
        if open_count >= shift.max_open_cases:
            raise ValueError("The agent has reached the maximum open investigation capacity")
        visit_count = int(db.query(func.count(Investigation.id)).filter(
            Investigation.assigned_agent_id == agent.id,
            Investigation.id != investigation.id,
            Investigation.region_code == investigation.region_code,
            Investigation.deleted_at.is_(None),
            Investigation.status.in_(("pending", "assigned")),
        ).scalar() or 0)
        if visit_count >= shift.max_visits:
            raise ValueError("The agent has reached the maximum visits for today's shift")
        def as_utc(value):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)

        shift_start = as_utc(shift.shift_starts_at)
        shift_end = as_utc(shift.shift_ends_at)
        earliest = max(
            shift_start,
            as_utc(investigation.visit_not_before_at) if investigation.visit_not_before_at else shift_start,
        )
        latest = min(
            shift_end,
            as_utc(investigation.visit_due_at) if investigation.visit_due_at else shift_end,
        )
        if earliest.timestamp() + investigation.service_duration_seconds > latest.timestamp():
            raise ValueError("The investigation service window does not fit this agent's shift")

    if active_assignment and active_assignment.agent_id == agent.id:
        active_assignment.note = note
        # Note changes alter pending plan inputs, but do not invalidate a
        # route already published for the same agent.
        db.query(PlanningRun).filter(
            PlanningRun.id.in_(affected_runs),
            PlanningRun.status.in_(("queued", "running", "ready")),
        ).update(
            {PlanningRun.status: "stale", PlanningRun.error_code: "assignment_changed"},
            synchronize_session=False,
        )
        from app.services.agent_schedules import enqueue_planning_trigger

        enqueue_planning_trigger(db, work_date, investigation.region_code, "manual_assignment_updated")
        if commit:
            db.commit()
            db.refresh(active_assignment)
        return active_assignment

    # A shared applied run may still be the valid route for agents untouched
    # by this reassignment, so clear only the old and new agents' pointers.
    from app.services.planning import clear_published_routes, planned_agent_ids_for_investigation

    clear_published_routes(
        db,
        affected_runs,
        sorted(
            set(planned_agent_ids_for_investigation(db, investigation.id))
            | {agent.id}
            | ({investigation.assigned_agent_id} if investigation.assigned_agent_id is not None else set())
        ),
    )
    db.query(PlanningRun).filter(
        PlanningRun.id.in_(affected_runs),
        PlanningRun.status.in_(("queued", "running", "ready")),
    ).update(
        {PlanningRun.status: "stale", PlanningRun.error_code: "assignment_changed"},
        synchronize_session=False,
    )

    if active_assignment:
        active_assignment.is_active = False
        active_assignment.unassigned_at = datetime.now(timezone.utc)

    assignment = InvestigationAssignment(
        investigation_id=investigation.id,
        agent_id=agent.id,
        assigned_by_id=assigned_by.id,
        assignment_source="manual",
        note=note,
    )
    investigation.assigned_agent_id = agent.id
    investigation.status = "assigned"

    db.add(assignment)
    from app.services.agent_schedules import enqueue_planning_trigger

    enqueue_planning_trigger(db, work_date, investigation.region_code, "manual_assignment_changed")
    if commit:
        db.commit()
        db.refresh(assignment)

    return assignment


def get_report(
    db: Session,
    investigation_id: int,
) -> InvestigationReport | None:
    return (
        db.query(InvestigationReport)
        .filter(InvestigationReport.investigation_id == investigation_id)
        .order_by(InvestigationReport.version.desc())
        .first()
    )


def get_report_versions(
    db: Session,
    investigation_id: int,
) -> list[InvestigationReport]:
    return (
        db.query(InvestigationReport)
        .filter(InvestigationReport.investigation_id == investigation_id)
        .order_by(InvestigationReport.version.desc())
        .all()
    )


def save_report_draft(
    db: Session,
    investigation: Investigation,
    author: User,
    data: ReportUpsert,
    route_revision: int | None = None,
    work_date: date | None = None,
) -> InvestigationReport:
    if author.role == "agent":
        if route_revision is not None or work_date is not None:
            from app.services.route_workflow import assert_current_action

            investigation = (
                db.query(Investigation)
                .filter(Investigation.id == investigation.id)
                .with_for_update()
                .populate_existing()
                .one()
            )
            if route_revision is None or work_date is None:
                raise ValueError("Refresh your route and include its current revision before saving this report")
            assert_current_action(
                db, investigation, author, work_date, route_revision,
                require_started=True,
            )
    report = get_report(db, investigation.id)

    if report is not None and report.status in {"submitted", "approved"}:
        raise ValueError("Submitted or approved report versions cannot be edited")

    starts_correction_revision = report is not None and (
        report.status == "returned_for_correction"
        or (investigation.status == "returned_for_correction" and report.status == "draft")
    )
    if report is None or starts_correction_revision:
        report = InvestigationReport(
            investigation_id=investigation.id,
            author_id=author.id,
            version=1 if report is None else report.version + 1,
            **data.model_dump(),
        )
        db.add(report)
    else:
        for field, value in data.model_dump().items():
            setattr(report, field, value)

    if investigation.status in {"assigned", "returned_for_correction"}:
        pending_revisit = db.query(AgentRevisitRequest).filter(
            AgentRevisitRequest.investigation_id == investigation.id,
            AgentRevisitRequest.status.in_(("waiting_for_shift", "queued", "routed")),
        ).first()
        if pending_revisit is None:
            investigation.status = "in_progress"

    db.commit()
    db.refresh(report)
    return report


def submit_report(
    db: Session,
    investigation: Investigation,
    actor: User | None = None,
    route_revision: int | None = None,
    work_date: date | None = None,
    now: datetime | None = None,
) -> InvestigationReport:
    # Serialize with route publication and assignment changes. Repeat the
    # controller's authorization check against the locked row before submit.
    investigation = (
        db.query(Investigation)
        .filter(Investigation.id == investigation.id)
        .with_for_update()
        .populate_existing()
        .one()
    )
    if actor is not None and (
        actor.role != "agent" or investigation.assigned_agent_id != actor.id
    ):
        raise ValueError("This investigation is no longer assigned to you")
    if actor is not None:
        if route_revision is not None or work_date is not None:
            from app.services.route_workflow import assert_current_action

            if route_revision is None or work_date is None:
                raise ValueError("Refresh your route and include its current revision before submitting this report")
            assert_current_action(
                db, investigation, actor, work_date, route_revision,
                require_started=True, now=now,
            )

    report = get_report(db, investigation.id)

    if report is None or not report.content.strip():
        raise ValueError("A non-empty report draft is required before submission")

    if report.status != "draft":
        raise ValueError("Only a draft report version can be submitted")

    if not report.visit_outcome:
        raise ValueError("Select a visit outcome before submitting the report")
    if not report.outcome:
        raise ValueError("Select an investigation outcome before submitting the report")
    if report.visit_outcome in {"visited", "no_access"} and report.visited_at is None:
        raise ValueError("Visit date and time are required for this visit outcome")
    if report.outcome == "verified" and not (report.verified_address or "").strip():
        raise ValueError("Verified address is required for a verified outcome")

    submitted_at = now or datetime.now(timezone.utc)
    if submitted_at.tzinfo is None:
        submitted_at = submitted_at.replace(tzinfo=timezone.utc)
    else:
        submitted_at = submitted_at.astimezone(timezone.utc)
    manila_now = submitted_at.astimezone(ZoneInfo("Asia/Manila"))
    visit_shift = None
    pending_assigned_visit = False
    if actor is not None:
        visit_shift = (
            db.query(AgentShift)
            .filter(
                AgentShift.agent_id == actor.id,
                AgentShift.work_date == manila_now.date(),
            )
            .with_for_update()
            .first()
        )
        if report.visited_at is not None:
            visit_at = _as_utc(report.visited_at)
            visit_work_date = visit_at.astimezone(ZoneInfo("Asia/Manila")).date()
            if visit_at > submitted_at:
                raise ValueError("The visit date and time cannot be in the future")
            if visit_work_date != manila_now.date():
                raise ValueError("A visit report must be submitted on the Manila workday when the visit occurred")
            if visit_shift is not None and visit_at < _as_utc(visit_shift.shift_starts_at):
                raise ValueError("The report visit time cannot be before the agent shift")
            if visit_shift is not None and visit_at > _as_utc(visit_shift.shift_ends_at):
                raise ValueError("The report visit date and time must be within the agent shift")
            if investigation.status == "pending":
                pending_assigned_visit = db.query(InvestigationAssignment.id).filter(
                    InvestigationAssignment.investigation_id == investigation.id,
                    InvestigationAssignment.agent_id == actor.id,
                    InvestigationAssignment.is_active.is_(True),
                ).with_for_update().first() is not None
        if (
            visit_shift is not None
            and submitted_at >= _as_utc(visit_shift.shift_ends_at)
            and report.visited_at is None
        ):
            raise ValueError("A visit timestamp is required for a report submitted after shift end")

    active_revisit = False
    if investigation.status == "assigned" and investigation.assigned_agent_id is not None:
        from app.models.agent_revisit import AgentRevisitRequest

        active_revisit = db.query(AgentRevisitRequest.id).filter(
            AgentRevisitRequest.investigation_id == investigation.id,
            AgentRevisitRequest.agent_id == investigation.assigned_agent_id,
            AgentRevisitRequest.status.in_(("queued", "routed")),
        ).first() is not None
    if (
        investigation.status not in {"in_progress", "returned_for_correction"}
        and not active_revisit
        and not pending_assigned_visit
    ):
        raise ValueError("Investigation is not ready for report submission")

    pending_revisit = None
    if investigation.assigned_agent_id is not None:
        from app.models.agent_revisit import AgentRevisitRequest

        pending_revisit = db.query(AgentRevisitRequest).filter(
            AgentRevisitRequest.investigation_id == investigation.id,
            AgentRevisitRequest.agent_id == investigation.assigned_agent_id,
            AgentRevisitRequest.status.in_(("waiting_for_shift", "queued", "routed")),
        ).order_by(AgentRevisitRequest.created_at.desc(), AgentRevisitRequest.id.desc()).first()
    if pending_revisit is not None and pending_revisit.status != "routed":
        raise ValueError("Wait for the revisit route to be published before submitting the correction report")
    if (
        pending_revisit is not None
        and pending_revisit.status == "routed"
        and report.visit_outcome in {"visited", "no_access"}
        and report.visited_at is not None
    ):
        revisit_visit_at = report.visited_at
        request_created_at = pending_revisit.created_at
        if revisit_visit_at.tzinfo is None:
            revisit_visit_at = revisit_visit_at.replace(tzinfo=timezone.utc)
        else:
            revisit_visit_at = revisit_visit_at.astimezone(timezone.utc)
        if request_created_at.tzinfo is None:
            request_created_at = request_created_at.replace(tzinfo=timezone.utc)
        else:
            request_created_at = request_created_at.astimezone(timezone.utc)
        if revisit_visit_at < request_created_at:
            raise ValueError("Enter the date and time of the requested revisit before submitting the correction report")

    report.status = "submitted"
    report.submitted_at = submitted_at
    investigation.status = "under_review"
    investigation.reopen_on = None

    from app.models.route_event import InvestigationRouteEvent

    active_attempts = db.query(InvestigationRouteEvent).filter(
        InvestigationRouteEvent.investigation_id == investigation.id,
        InvestigationRouteEvent.agent_id == investigation.assigned_agent_id,
        InvestigationRouteEvent.work_date == (work_date or manila_now.date()),
        InvestigationRouteEvent.event_type == "no_contact",
        InvestigationRouteEvent.state == "retrying",
    ).with_for_update().all()
    for attempt in active_attempts:
        attempt.state = "resolved"
        attempt.finalized_at = submitted_at
        if attempt.parent_event_id is not None:
            parent_attempt = db.get(InvestigationRouteEvent, attempt.parent_event_id)
            if parent_attempt is not None:
                parent_attempt.state = "resolved"
                parent_attempt.finalized_at = submitted_at

    if investigation.assigned_agent_id is not None:
        submitted_at = report.submitted_at.astimezone(timezone.utc)
        if (
            report.visit_outcome in {"visited", "no_access"}
            and report.visited_at is not None
            and investigation.location_confirmed
            and investigation.latitude is not None
            and investigation.longitude is not None
        ):
            visited_at = report.visited_at
            if visited_at.tzinfo is None:
                visited_at = visited_at.replace(tzinfo=timezone.utc)
            else:
                visited_at = visited_at.astimezone(timezone.utc)
            visit_work_date = visited_at.astimezone(ZoneInfo("Asia/Manila")).date()
            visit_shift = db.query(AgentShift).filter(
                AgentShift.agent_id == investigation.assigned_agent_id,
                AgentShift.work_date == visit_work_date,
            ).with_for_update().first()
            if visit_shift is not None:
                shift_start = visit_shift.shift_starts_at
                if shift_start.tzinfo is None:
                    shift_start = shift_start.replace(tzinfo=timezone.utc)
                else:
                    shift_start = shift_start.astimezone(timezone.utc)
                last_completed_at = visit_shift.last_completed_at
                if last_completed_at is not None:
                    if last_completed_at.tzinfo is None:
                        last_completed_at = last_completed_at.replace(tzinfo=timezone.utc)
                    else:
                        last_completed_at = last_completed_at.astimezone(timezone.utc)
                if (
                    shift_start <= visited_at
                    and visited_at <= submitted_at
                    and (last_completed_at is None or last_completed_at <= visited_at)
                ):
                    visit_shift.last_completed_investigation_id = investigation.id
                    visit_shift.last_completed_report_id = report.id
                    visit_shift.last_completed_at = visited_at
                    visit_shift.last_completed_latitude = investigation.latitude
                    visit_shift.last_completed_longitude = investigation.longitude
                    if (
                        visit_work_date == manila_now.date()
                        and visit_shift.is_available
                        and submitted_at < _as_utc(visit_shift.shift_ends_at)
                    ):
                        visit_shift.current_planning_run_id = None

        from app.services.agent_revisits import complete_agent_revisit_requests

        complete_agent_revisit_requests(db, investigation.id, report.id, submitted_at)
        from app.services.agent_schedules import enqueue_planning_trigger

        enqueue_planning_trigger(db, manila_now.date(), investigation.region_code, "agent_report_submitted")

    db.commit()
    db.refresh(report)
    return report


def get_review_history(
    db: Session,
    investigation_id: int,
) -> list[InvestigationReview]:
    return (
        db.query(InvestigationReview)
        .filter(InvestigationReview.investigation_id == investigation_id)
        .order_by(InvestigationReview.reviewed_at.desc())
        .all()
    )


def review_investigation_report(
    db: Session,
    investigation: Investigation,
    reviewer: User,
    decision: str,
    comments: str | None,
) -> InvestigationReview:
    report = get_report(db, investigation.id)

    if report is None or report.status != "submitted":
        raise ValueError("A submitted report is required for review")

    if investigation.status != "under_review":
        raise ValueError("Investigation is not awaiting review")

    if decision == "returned_for_correction" and not comments:
        raise ValueError("Comments are required when returning a report")

    review = InvestigationReview(
        investigation_id=investigation.id,
        report_id=report.id,
        reviewer_id=reviewer.id,
        decision=decision,
        comments=comments,
    )

    if decision == "approved":
        report.status = "approved"
        investigation.status = "completed"
    else:
        report.status = "returned_for_correction"
        investigation.status = "returned_for_correction"

    db.add(review)
    db.commit()
    db.refresh(review)
    return review

def delete_investigation(
    db: Session,
    investigation: Investigation,
    actor: User,
) -> None:
    from app.models.planning import PlanningItem, PlanningRun

    investigation = (
        db.query(Investigation)
        .filter(Investigation.id == investigation.id)
        .with_for_update()
        .one()
    )
    investigation.deleted_at = datetime.now(timezone.utc)
    affected_runs = select(PlanningItem.planning_run_id).where(
        PlanningItem.investigation_id == investigation.id,
    )
    from app.services.planning import clear_published_routes, planned_agent_ids_for_investigation

    clear_published_routes(
        db,
        affected_runs,
        sorted(
            set(planned_agent_ids_for_investigation(db, investigation.id))
            | ({investigation.assigned_agent_id} if investigation.assigned_agent_id is not None else set())
        ),
    )
    db.query(PlanningRun).filter(
        PlanningRun.id.in_(affected_runs), PlanningRun.status.in_(("queued", "running", "ready")),
    ).update({PlanningRun.status: "stale", PlanningRun.error_code: "investigation_deleted"}, synchronize_session=False)
    db.add(ActivityLog(
        actor_id=actor.id,
        action="investigation.deleted",
        object_type="investigation",
        object_id=investigation.id,
        details={"reference_number": investigation.reference_number},
    ))
    db.commit()


def permanently_delete_investigation(
    db: Session,
    investigation: Investigation,
    actor: User,
) -> None:
    reference_number = investigation.reference_number
    investigation_id = investigation.id

    # Delete dependents in foreign-key order so this works consistently with
    # databases that enforce constraints even when ORM relationships are unloaded.
    db.query(InvestigationReview).filter(
        InvestigationReview.investigation_id == investigation_id
    ).delete(synchronize_session=False)
    db.query(InvestigationReport).filter(
        InvestigationReport.investigation_id == investigation_id
    ).delete(synchronize_session=False)
    db.query(InvestigationAssignment).filter(
        InvestigationAssignment.investigation_id == investigation_id
    ).delete(synchronize_session=False)
    db.add(ActivityLog(
        actor_id=actor.id,
        action="investigation.permanently_deleted",
        object_type="investigation",
        object_id=investigation_id,
        details={"reference_number": reference_number},
    ))
    db.delete(investigation)
    db.commit()
