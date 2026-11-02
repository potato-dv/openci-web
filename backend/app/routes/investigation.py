from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select, func, case
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload

from app.controllers.investigation import (
    assign,
    create,
    create_revisit_request,
    delete,
    get_trash,
    get_investigation_report,
    get_investigation_report_versions,
    read_revisit_request,
    get_one,
    review_report,
    permanently_delete,
    restore,
    save_investigation_report,
    submit_investigation_report,
    update,
)
from app.database.session import get_db
from app.models.assignment import InvestigationAssignment
from app.models.activity import ActivityLog
from app.models.investigation import Investigation
from app.models.planning import PlanningItem, PlanningRun
from app.models.review import InvestigationReview
from app.models.user import User
from app.schemas.investigation import InvestigationCreate, InvestigationResponse, InvestigationUpdate, InvestigationPageResponse
from app.schemas.assignment import AssignmentCreate, AssignmentResponse
from app.schemas.report import ReportResponse, ReportUpsert, RevisitRequestResponse
from app.schemas.review import ReviewCreate, ReviewResponse
from app.schemas.planning import GeocodeCandidate, LocationConfirm, LocationResponse
from app.services.search import investigation_search, subject_expression
from app.services.geocoding import suggest_locations
from app.services.geospatial import cells_for_point
from app.utils.auth import get_current_user, require_roles
from app.utils.features import require_planning_enabled

router = APIRouter(
    prefix="/investigations",
    tags=["Investigations"],
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
    dependencies=[Depends(require_planning_enabled)],
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
    response_model=RevisitRequestResponse | None,
    dependencies=[Depends(require_planning_enabled)],
)
def get_revisit_request_for_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    request = read_revisit_request(db, investigation_id, current_user)
    if request is None:
        return None
    return {
        **{field: getattr(request, field) for field in (
            "id", "investigation_id", "report_id", "agent_id", "target_work_date",
            "status", "planning_run_id", "created_at", "completed_at",
        )},
        "reference_number": db.query(Investigation.reference_number).filter(Investigation.id == request.investigation_id).scalar(),
    }


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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
):
    return save_investigation_report(db, investigation_id, data, current_user)


@router.post(
    "/{investigation_id}/report/submit",
    response_model=ReportResponse,
)
def submit_report_for_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return submit_investigation_report(db, investigation_id, current_user)


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
    dependencies=[Depends(require_planning_enabled)],
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
    if assignment.auto_route_status not in {"failed", "partially_published"}:
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
