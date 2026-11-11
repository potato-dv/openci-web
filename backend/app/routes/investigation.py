from datetime import date, datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select, func, case, and_, or_
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header, Response
from sqlalchemy.orm import Session, joinedload

from app.controllers.investigation import (
    assign,
    create,
    create_revisit_request,
    delete,
    get_trash,
    get_investigation_report,
    get_investigation_report_versions,
    read_revisit_request_state,
    get_one,
    review_report,
    permanently_delete,
    restore,
    save_investigation_report,
    submit_investigation_report,
    submit_automatic_assignment,
    unassign,
    update,
)
from app.database.session import get_db
from app.dependencies.rate_limit import general_api_rate_limit, planning_enqueue_rate_limit
from app.models.assignment import InvestigationAssignment
from app.models.activity import ActivityLog
from app.models.investigation import Investigation
from app.models.planning import PlanningItem, PlanningRun
from app.models.review import InvestigationReview
from app.models.user import User
from app.models.route_event import InvestigationRouteEvent
from app.schemas.agent_permissions import InvestigationActivityResponse, RevisitRequestState
from app.schemas.investigation import InvestigationCreate, InvestigationResponse, InvestigationUpdate, InvestigationPageResponse
from app.schemas.assignment import AssignmentCreate, AssignmentResponse
from app.schemas.report import ReportResponse, ReportUpsert, RevisitRequestResponse
from app.schemas.review import ReviewCreate, ReviewResponse
from app.schemas.planning import GeocodeCandidate, LocationConfirm, LocationResponse
from app.schemas.route_event import (
    NoContactFinalizeInput,
    NoContactReviewQueueResponse,
    RouteActionInput,
    RouteActionResponse,
    RouteEventResponse,
    UnableToProceedInput,
)
from app.services.route_workflow import (
    RouteActionConflict,
    cancel_no_contact_event,
    finalize_no_contact_attempt,
    record_unable_to_proceed,
    start_current_investigation,
)
from app.services.search import investigation_search, subject_expression
from app.services.geocoding import suggest_locations
from app.services.geospatial import cells_for_point
from app.services.agent_permissions import is_agent_feature_allowed, require_agent_feature
from app.utils.auth import get_current_user, require_roles
from app.utils.features import require_planning_enabled

router = APIRouter(
    prefix="/investigations",
    tags=["Investigations"],
    dependencies=[Depends(general_api_rate_limit)],
    )


@router.get(
    "/{investigation_id}/geocode-suggestions",
    response_model=list[GeocodeCandidate],
    dependencies=[Depends(require_planning_enabled)],
)
def geocode_investigation_address(
    investigation_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "supervisor")),
):
    investigation = db.query(Investigation).filter(
        Investigation.id == investigation_id,
        Investigation.deleted_at.is_(None),
    ).first()
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    try:
        return suggest_locations(investigation)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get(
    "/{investigation_id}/location",
    response_model=LocationResponse | None,
    dependencies=[Depends(require_planning_enabled)],
)
def get_investigation_location(
    investigation_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "supervisor")),
):
    investigation = db.query(Investigation).filter(
        Investigation.id == investigation_id,
        Investigation.deleted_at.is_(None),
    ).first()
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    if investigation.latitude is None:
        return None
    return {
        "latitude": investigation.latitude,
        "longitude": investigation.longitude,
        "source": investigation.location_source or "manual",
        "provider_ref": investigation.location_provider_ref,
        "confirmed_at": investigation.location_confirmed_at,
        "h3_r7": investigation.h3_r7,
        "h3_r8": investigation.h3_r8,
        "h3_r9": investigation.h3_r9,
    }


@router.put(
    "/{investigation_id}/location",
    response_model=InvestigationResponse,
    dependencies=[Depends(require_planning_enabled), Depends(planning_enqueue_rate_limit)],
)
def confirm_investigation_location(
    investigation_id: int,
    data: LocationConfirm,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("admin", "supervisor")),
):
    investigation = db.query(Investigation).filter(
        Investigation.id == investigation_id,
        Investigation.deleted_at.is_(None),
    ).with_for_update().first()
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    if data.source == "manual" and data.provider_ref:
        raise HTTPException(status_code=422, detail="Manual locations cannot include a provider reference")
    if (
        investigation.location_confirmed
        and investigation.latitude == data.latitude
        and investigation.longitude == data.longitude
        and investigation.location_source == data.source
        and investigation.location_provider_ref == data.provider_ref
    ):
        return investigation
    actor_id = actor.id
    cells = cells_for_point(data.latitude, data.longitude)
    investigation.latitude = data.latitude
    investigation.longitude = data.longitude
    investigation.location_source = data.source
    investigation.location_provider_ref = data.provider_ref
    investigation.location_confirmed_at = datetime.now(timezone.utc)
    investigation.location_confirmed_by_id = actor_id
    investigation.h3_r7 = cells["h3_r7"]
    investigation.h3_r8 = cells["h3_r8"]
    investigation.h3_r9 = cells["h3_r9"]
    ready_run_ids = select(PlanningItem.planning_run_id).where(
        PlanningItem.investigation_id == investigation.id
    )
    published_run_ids = select(PlanningItem.planning_run_id).where(
        PlanningItem.investigation_id == investigation.id,
    )
    from app.services.planning import clear_published_routes, planned_agent_ids_for_investigation

    clear_published_routes(
        db,
        published_run_ids,
        sorted(
            set(planned_agent_ids_for_investigation(db, investigation.id))
            | ({investigation.assigned_agent_id} if investigation.assigned_agent_id is not None else set())
        ),
    )
    db.query(PlanningRun).filter(
        PlanningRun.id.in_(ready_run_ids), PlanningRun.status.in_(("queued", "running", "ready"))
    ).update({PlanningRun.status: "stale", PlanningRun.error_code: "location_changed"}, synchronize_session=False)
    db.add(ActivityLog(
        actor_id=actor_id,
        action="investigation.location_confirmed",
        object_type="investigation",
        object_id=investigation.id,
        details={"source": data.source},
    ))
    from app.services.agent_schedules import enqueue_planning_trigger

    enqueue_planning_trigger(db, datetime.now(ZoneInfo("Asia/Manila")).date(), investigation.region_code, "investigation_location_confirmed")
    db.commit()
    db.refresh(investigation)
    if investigation.region_code and investigation.status in {"pending", "assigned"}:
        from app.services.planning import queue_automatic_planning

        try:
            queue_automatic_planning(db, investigation.region_code, actor)
        except Exception:
            # Location confirmation is durable even when the broker is down;
            # planning failure is surfaced by the planning run when it exists.
            import logging

            logging.getLogger("app.planning").exception(
                "Could not queue automatic planning after location confirmation"
            )
    return investigation


@router.get(
    "/{investigation_id}/reviews",
    response_model=list[ReviewResponse],
)
def list_reviews_for_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_one(db, investigation_id, current_user)
    return (
        db.query(InvestigationReview)
        .options(joinedload(InvestigationReview.reviewer))
        .filter(InvestigationReview.investigation_id == investigation_id)
        .order_by(InvestigationReview.reviewed_at.desc())
        .all()
    )


@router.post(
    "/{investigation_id}/reviews",
    response_model=ReviewResponse,
)
def review_investigation(
    investigation_id: int,
    data: ReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "supervisor")),
):
    return review_report(db, investigation_id, data, current_user)


@router.get(
    "/{investigation_id}/report",
    response_model=ReportResponse | None,
)
def get_report_for_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_investigation_report(db, investigation_id, current_user)


@router.get(
    "/{investigation_id}/revisit-request",
    response_model=RevisitRequestState,
    dependencies=[Depends(require_planning_enabled)],
)
def get_revisit_request_for_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    state_data = read_revisit_request_state(db, investigation_id, current_user)
    request = state_data["request"]
    if request is None:
        return {"request": None, "can_request": state_data["can_request"]}
    return {"request": {
        **{field: getattr(request, field) for field in (
            "id", "investigation_id", "report_id", "agent_id", "target_work_date",
            "status", "planning_run_id", "created_at", "completed_at",
        )},
        "reference_number": db.query(Investigation.reference_number).filter(Investigation.id == request.investigation_id).scalar(),
    }, "can_request": state_data["can_request"]}


@router.post(
    "/{investigation_id}/revisit-request",
    response_model=RevisitRequestResponse,
    dependencies=[Depends(require_planning_enabled)],
)
def request_revisit_for_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_agent_feature(db, current_user, "investigation.request_revisit")
    request = create_revisit_request(db, investigation_id, current_user)
    return {
        **{field: getattr(request, field) for field in (
            "id", "investigation_id", "report_id", "agent_id", "target_work_date",
            "status", "planning_run_id", "created_at", "completed_at",
        )},
        "reference_number": db.query(Investigation.reference_number).filter(Investigation.id == request.investigation_id).scalar(),
    }


@router.get(
    "/{investigation_id}/reports",
    response_model=list[ReportResponse],
)
def list_report_versions_for_investigation(
    investigation_id: int,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    response.headers["Cache-Control"] = "private, no-store"
    return get_investigation_report_versions(db, investigation_id, current_user)


@router.put(
    "/{investigation_id}/report",
    response_model=ReportResponse,
)
def save_report_for_investigation(
    investigation_id: int,
    data: ReportUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    work_date: date = Query(...),
    route_revision: int = Header(..., alias="X-Route-Revision", gt=0),
):
    return save_investigation_report(
        db, investigation_id, data, current_user,
        route_revision=route_revision,
        work_date=work_date,
    )


@router.post(
    "/{investigation_id}/report/submit",
    response_model=ReportResponse,
)
def submit_report_for_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    work_date: date = Query(...),
    route_revision: int = Header(..., alias="X-Route-Revision", gt=0),
):
    return submit_investigation_report(
        db, investigation_id, current_user,
        route_revision=route_revision,
        work_date=work_date,
    )


@router.post(
    "/{investigation_id}/start",
    response_model=RouteActionResponse,
    dependencies=[Depends(require_planning_enabled)],
)
def start_route_investigation(
    investigation_id: int,
    data: RouteActionInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("agent")),
):
    try:
        return start_current_investigation(
            db, investigation_id, current_user, data.work_date, data.route_revision,
        )
    except RouteActionConflict as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="This route action was recorded concurrently. Refresh your route.") from error


@router.post(
    "/{investigation_id}/unable-to-proceed",
    response_model=RouteEventResponse,
    dependencies=[Depends(require_planning_enabled)],
)
def unable_to_proceed(
    investigation_id: int,
    data: UnableToProceedInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("agent")),
):
    try:
        event = record_unable_to_proceed(
            db, investigation_id, current_user, data.work_date, data.route_revision,
            data.reason, data.notes, data.contact_available_from,
            data.contact_available_until,
        )
        try:
            from app.workers.tasks import dispatch_planning_triggers_task

            dispatch_planning_triggers_task.delay()
        except Exception:
            import logging

            logging.getLogger("app.planning").exception("Could not dispatch route refresh after no-contact attempt")
        return event
    except RouteActionConflict as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="This attempt was already recorded. Refresh your route.") from error


@router.post(
    "/{investigation_id}/no-contact-report",
    response_model=RouteEventResponse,
    dependencies=[Depends(require_planning_enabled)],
)
def submit_no_contact_report(
    investigation_id: int,
    data: NoContactFinalizeInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("agent")),
):
    event = db.query(InvestigationRouteEvent).filter(
        InvestigationRouteEvent.id == data.event_id,
        InvestigationRouteEvent.investigation_id == investigation_id,
    ).first()
    if event is None:
        raise HTTPException(status_code=404, detail="No-contact attempt not found")
    try:
        return finalize_no_contact_attempt(
            db, event.id, current_user, data.work_date, data.route_revision,
        )
    except RouteActionConflict as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post(
    "/{investigation_id}/no-contact-events/{event_id}/cancel",
    response_model=InvestigationResponse,
    dependencies=[Depends(require_planning_enabled)],
)
def cancel_investigation_no_contact(
    investigation_id: int,
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "supervisor")),
):
    try:
        case = cancel_no_contact_event(db, investigation_id, event_id, current_user)
        try:
            from app.workers.tasks import dispatch_planning_triggers_task

            dispatch_planning_triggers_task.delay()
        except Exception:
            import logging

            logging.getLogger("app.planning").exception(
                "Could not dispatch planning triggers after admin cancellation"
            )
        return case
    except RouteActionConflict as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post(
    "/{investigation_id}/assign",
    response_model=AssignmentResponse,
)
def assign_investigation_to_agent(
    investigation_id: int,
    data: AssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "supervisor")),
):
    return assign(db, investigation_id, data, current_user)


@router.delete(
    "/{investigation_id}/assignment",
    response_model=InvestigationResponse,
)
def unassign_investigation_from_agent(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "supervisor")),
):
    return unassign(db, investigation_id, current_user)


@router.post(
    "/{investigation_id}/automatic-assignment",
    response_model=InvestigationResponse,
    dependencies=[Depends(require_planning_enabled), Depends(planning_enqueue_rate_limit)],
)
def submit_investigation_for_automatic_assignment(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "supervisor")),
):
    return submit_automatic_assignment(db, investigation_id, current_user)


@router.get(
    "/{investigation_id}/assignments",
    response_model=list[AssignmentResponse],
)
def list_investigation_assignments(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "supervisor")),
):
    get_one(db, investigation_id, current_user)
    return (
        db.query(InvestigationAssignment)
        .options(
            joinedload(InvestigationAssignment.agent),
            joinedload(InvestigationAssignment.assigned_by),
        )
        .filter_by(investigation_id=investigation_id)
        .order_by(InvestigationAssignment.assigned_at.desc())
        .all()
    )


@router.post(
    "/{investigation_id}/route-refresh",
    response_model=AssignmentResponse,
    dependencies=[Depends(require_planning_enabled), Depends(planning_enqueue_rate_limit)],
)
def retry_investigation_route_refresh(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "supervisor")),
):
    get_one(db, investigation_id, current_user)
    assignment = (
        db.query(InvestigationAssignment)
        .filter(
            InvestigationAssignment.investigation_id == investigation_id,
            InvestigationAssignment.is_active.is_(True),
        )
        .with_for_update()
        .first()
    )
    if assignment is None:
        raise HTTPException(status_code=409, detail="No active assignment is available to refresh")
    if assignment.auto_route_status in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="The route refresh is already in progress")
    if assignment.auto_route_status not in {"failed", "partially_published", "unscheduled"}:
        raise HTTPException(status_code=409, detail="Only a failed route refresh can be retried")

    from app.services.planning import queue_assignment_route_refresh

    return queue_assignment_route_refresh(
        db,
        assignment.id,
        assignment.auto_route_agent_ids or [assignment.agent_id],
        current_user,
    )

@router.get("/", response_model=InvestigationPageResponse)
def get_investigations(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
    q: str = "", status: str | None = None, priority: str | None = None,
    assigned_agent_id: int | None = None, location_confirmed: bool | None = None,
    sort: Literal["created_at", "reference_number", "subject_name", "priority", "status"] = "created_at",
    direction: Literal["asc", "desc"] = "desc", page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
):
    base = db.query(Investigation).filter(Investigation.deleted_at.is_(None))
    if current_user.role == "agent":
        base = base.filter(Investigation.assigned_agent_id == current_user.id)
        if not is_agent_feature_allowed(db, current_user, "investigation.view_own_history"):
            base = base.filter(Investigation.status != "completed")
    status_counts = dict(base.with_entities(Investigation.status, func.count(Investigation.id)).group_by(Investigation.status).all())
    priority_counts = dict(base.with_entities(Investigation.priority, func.count(Investigation.id)).group_by(Investigation.priority).all())
    confirmed = (Investigation.latitude.is_not(None) & Investigation.longitude.is_not(None) & Investigation.location_confirmed_at.is_not(None))
    facets = {"status": {key: status_counts.get(key, 0) for key in ("pending", "assigned", "in_progress", "under_review", "returned_for_correction", "completed", "cancelled")},
        "priority": {key: priority_counts.get(key, 0) for key in ("normal", "high", "urgent")},
        "assigned": base.filter(Investigation.assigned_agent_id.is_not(None)).count(),
        "unassigned": base.filter(Investigation.assigned_agent_id.is_(None)).count(),
        "location_unconfirmed": base.filter(~confirmed).count()}
    query = base
    if q.strip():
        query = query.filter(investigation_search(q))
    if status:
        query = query.filter(Investigation.status == status)
    if priority:
        query = query.filter(Investigation.priority == priority)
    if assigned_agent_id is not None:
        query = query.filter(Investigation.assigned_agent_id == assigned_agent_id if assigned_agent_id else Investigation.assigned_agent_id.is_(None))
    if location_confirmed is not None:
        query = query.filter(confirmed if location_confirmed else ~confirmed)
    total = query.count()
    if sort == "subject_name":
        column = subject_expression()
    elif sort == "priority":
        column = case({"normal": 0, "high": 1, "urgent": 2}, value=Investigation.priority)
    else:
        column = getattr(Investigation, sort)
    rows = query.options(joinedload(Investigation.assigned_agent)).order_by(column.desc() if direction == "desc" else column.asc(), Investigation.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [InvestigationResponse.model_validate(row) for row in rows], "total": total, "page": page, "page_size": page_size, "facets": facets}

@router.post("/", response_model=InvestigationResponse)
def create_investigation(
    data: InvestigationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "supervisor")),
):
    return create(db, data, current_user)


@router.get("/trash", response_model=list[InvestigationResponse])
@router.get("/archived", response_model=list[InvestigationResponse], include_in_schema=False)
def list_trash(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "supervisor")),
):
    return get_trash(db)


@router.get("/awaiting-no-contact-review", response_model=NoContactReviewQueueResponse)
def awaiting_no_contact_review(
    q: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    sort: Literal["attempted_at", "reference_number"] = "attempted_at",
    direction: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "supervisor")),
):
    agent_finalized_event_roots = (
        db.query(
            func.coalesce(
                InvestigationRouteEvent.parent_event_id,
                InvestigationRouteEvent.id,
            )
        )
        .join(
            ActivityLog,
            ActivityLog.details["route_event_id"].as_integer() == InvestigationRouteEvent.id,
        )
        .filter(
            ActivityLog.action == "investigation.cancelled_no_contact_finalized",
            InvestigationRouteEvent.event_type == "no_contact",
        )
    )
    open_attempt = InvestigationRouteEvent.state.in_(
        ("deferred", "retrying", "retry_failed"),
    )
    finalized_submission_waiting_for_reopen = and_(
        InvestigationRouteEvent.state == "carried_over",
        InvestigationRouteEvent.id.in_(agent_finalized_event_roots),
        Investigation.status == "cancelled",
        Investigation.reopen_on.is_not(None),
        InvestigationRouteEvent.next_work_date == Investigation.reopen_on,
    )
    query = (
        db.query(InvestigationRouteEvent, Investigation)
        .join(Investigation, Investigation.id == InvestigationRouteEvent.investigation_id)
        .filter(
            InvestigationRouteEvent.event_type == "no_contact",
            InvestigationRouteEvent.parent_event_id.is_(None),
            Investigation.deleted_at.is_(None),
            or_(open_attempt, finalized_submission_waiting_for_reopen),
        )
    )
    if q.strip():
        query = query.filter(investigation_search(q))
    total = query.count()
    column = Investigation.reference_number if sort == "reference_number" else InvestigationRouteEvent.attempted_at
    rows = (
        query.options(joinedload(Investigation.assigned_agent))
        .order_by(column.desc() if direction == "desc" else column.asc(), InvestigationRouteEvent.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "event_id": event.id,
                "investigation_id": case.id,
                "reference_number": case.reference_number,
                "subject_name": case.subject_name,
                "assigned_agent_name": case.assigned_agent_name,
                "priority": case.priority,
                "reason": event.reason,
                "state": event.state,
                "retry_number": event.retry_number,
                "attempted_at": event.attempted_at,
                "work_date": event.work_date,
                "next_work_date": event.next_work_date,
                "notes": event.notes,
            }
            for event, case in rows
        ],
    }


@router.post("/{investigation_id}/restore", response_model=InvestigationResponse)
def restore_trashed_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "supervisor")),
):
    return restore(db, investigation_id, current_user)

@router.get("/{investigation_id}", response_model=InvestigationResponse)
def get_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_one(db, investigation_id, current_user)


@router.get("/{investigation_id}/activity-history", response_model=InvestigationActivityResponse)
def get_investigation_activity_history(
    investigation_id: int,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("agent")),
):
    require_agent_feature(db, current_user, "investigation.view_own_history")
    get_one(db, investigation_id, current_user)
    safe_actions = {
        "investigation.created": "Investigation created",
        "investigation.assigned": "Investigation assigned",
        "investigation.unassigned": "Investigation unassigned",
        "investigation.updated": "Investigation details updated",
        "investigation.revisit_requested": "Revisit requested",
        "investigation.route_stop_started": "Visit started",
        "investigation.no_contact_deferred": "Visit deferred",
        "investigation.cancelled_no_contact_finalized": "No-contact report submitted",
        "report.saved": "Report draft saved",
        "report.submitted": "Report submitted",
        "report.reviewed": "Report reviewed",
    }
    rows = db.query(ActivityLog).options(joinedload(ActivityLog.actor)).filter(
        ActivityLog.object_type == "investigation",
        ActivityLog.object_id == investigation_id,
        ActivityLog.action.in_(tuple(safe_actions)),
    ).order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc()).limit(100).all()
    response.headers["Cache-Control"] = "private, no-store"
    return {"items": [
        {
            "id": row.id,
            "label": safe_actions[row.action],
            "actor_name": row.actor.name if row.actor else None,
            "created_at": row.created_at,
        }
        for row in rows
    ]}

@router.patch("/{investigation_id}", response_model=InvestigationResponse)
def update_investigation(
    investigation_id: int,
    data: InvestigationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return update(db, investigation_id, data, current_user)

@router.delete("/{investigation_id}")
def delete_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "supervisor")),
):
    return delete(db, investigation_id, current_user)


@router.delete("/{investigation_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
def permanently_delete_investigation_route(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    permanently_delete(db, investigation_id, current_user)
