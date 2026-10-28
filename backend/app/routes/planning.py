from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.activity import ActivityLog
from app.models.assignment import InvestigationAssignment
from app.models.investigation import Investigation
from app.models.planning import AgentShift, PlanningItem, PlanningRun, PlanningRoute
from app.models.user import User
from app.schemas.planning import (
    AgentShiftInput,
    AgentRouteResponse,
    AgentRosterResponse,
    AgentShiftResponse,
    GeocodeCandidate,
    LocationConfirm,
    PlanningReadinessResponse,
    PlanningMapDataResponse,
    PlanningRunResponse,
    PlanningServiceStatusResponse,
    PlanningRouteOverviewResponse,
    PlanningDashboardResponse,
)
from app.services.geocoding import suggest_locations
from app.services.geospatial import cells_for_point
from app.services.planning import (
    OPEN_STATUSES,
    PlanningConflict,
    get_run,
    readiness,
    planning_map_data,
    run_response,
    set_agent_shift,
    route_response,
    planning_route_overview,
    planning_dashboard,
    queue_automatic_planning,
    queue_shift_route_refresh,
)
from app.services.planning_status import get_planning_service_status
from app.utils.auth import require_roles
from app.utils.features import require_planning_enabled


router = APIRouter(
    prefix="/planning",
    tags=["Planning"],
    dependencies=[Depends(require_planning_enabled)],
)


@router.get("/agents/{agent_id}/shifts/{work_date}", response_model=AgentShiftResponse | None)
def get_agent_shift(
    agent_id: int,
    work_date: date,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "supervisor")),
):
    agent = db.query(User).filter(User.id == agent_id, User.role == "agent").first()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return db.query(AgentShift).filter(
        AgentShift.agent_id == agent_id,
        AgentShift.work_date == work_date,
    ).first()


@router.put("/agents/{agent_id}/shifts/{work_date}", response_model=AgentShiftResponse)
def put_agent_shift(
    agent_id: int,
    work_date: date,
    data: AgentShiftInput,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("admin", "supervisor")),
):
    if data.work_date != work_date:
        raise HTTPException(status_code=422, detail="Path date and body work_date must match")
    try:
        shift = set_agent_shift(db, agent_id, data, commit=False)
    except PlanningConflict as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    db.add(ActivityLog(
        actor_id=actor.id,
        action="agent.shift_updated",
        object_type="agent_shift",
        object_id=shift.id,
        details={"agent_id": agent_id, "work_date": str(work_date), "available": data.is_available},
    ))
    db.commit()
    db.refresh(shift)
    # A shift edit can change eligibility, capacity, or route geometry. Replan
    # all confirmed unassigned work in the affected date and region.
    queue_shift_route_refresh(db, agent_id, work_date, actor)
    return shift


@router.get("/readiness", response_model=PlanningReadinessResponse)
def get_readiness(
    work_date: date,
    region_code: str,
    resolution: int = 8,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "supervisor")),
):
    try:
        return readiness(db, work_date, region_code, resolution)
    except PlanningConflict as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/map-data", response_model=PlanningMapDataResponse)
def get_planning_map_data(
    work_date: date,
    region_code: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "supervisor")),
):
    try:
        return planning_map_data(db, work_date, region_code)
    except PlanningConflict as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/route-overview", response_model=PlanningRouteOverviewResponse)
def get_planning_route_overview(
    work_date: date,
    region_code: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "supervisor")),
):
    try:
        return planning_route_overview(db, work_date, region_code)
    except PlanningConflict as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/dashboard", response_model=PlanningDashboardResponse)
def get_planning_dashboard(
    work_date: date,
    region_code: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "supervisor")),
):
    try:
        return planning_dashboard(db, work_date, region_code)
    except PlanningConflict as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/service-status", response_model=PlanningServiceStatusResponse)
def get_service_status(
    refresh: bool = False,
    _: User = Depends(require_roles("admin", "supervisor")),
):
    return get_planning_service_status(force=refresh)


@router.get("/runs/{run_id}", response_model=PlanningRunResponse)
def get_planning_run(
    run_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "supervisor")),
):
    run = get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Planning run not found")
    return run_response(db, run)


@router.post("/investigations/{investigation_id}/retry", response_model=PlanningRunResponse)
def retry_automatic_planning(
    investigation_id: int,
    work_date: date,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("admin", "supervisor")),
):
    investigation = db.query(Investigation).filter(
        Investigation.id == investigation_id,
        Investigation.deleted_at.is_(None),
    ).first()
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    if not investigation.location_confirmed:
        raise HTTPException(status_code=409, detail="Confirm the investigation location before retrying planning")
    if not investigation.region_code:
        raise HTTPException(status_code=409, detail="Set an investigation service region before retrying planning")
    try:
        run = queue_automatic_planning(db, investigation.region_code, actor, work_date)
    except PlanningConflict as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if run is None:
        raise HTTPException(status_code=409, detail="No eligible investigations are waiting for planning in this scope")
    return run_response(db, run)


def published_agent_route(db: Session, agent: User, work_date: date) -> dict:
    shift = db.query(AgentShift).filter(AgentShift.agent_id == agent.id, AgentShift.work_date == work_date).first()
    empty = {"work_date": work_date, "shift": shift, "route": None, "stops": []}
    if shift is None:
        return empty | {"reason": "no_shift"}
    if not shift.is_available:
        return empty | {"reason": "shift_unavailable"}

    def route_refresh_reason() -> str:
        auto_runs = db.query(PlanningRun).filter(
            PlanningRun.work_date == work_date,
            PlanningRun.region_code == shift.region_code,
            PlanningRun.auto_publish.is_(True),
            PlanningRun.status.in_(("queued", "running", "ready", "failed")),
        ).order_by(PlanningRun.id.desc()).all()
        active = next((
            candidate for candidate in auto_runs
            if agent.id in (candidate.agent_ids or [])
            and candidate.status in {"queued", "running", "ready"}
        ), None)
        if active:
            return "route_refresh_pending"
        has_confirmed_work = db.query(Investigation.id).filter(
            Investigation.assigned_agent_id == agent.id,
            Investigation.deleted_at.is_(None),
            Investigation.status.in_(("pending", "assigned")),
            Investigation.region_code == shift.region_code,
            Investigation.location_confirmed_at.is_not(None),
            Investigation.latitude.is_not(None),
            Investigation.longitude.is_not(None),
        ).first() is not None
        return "route_needs_refresh" if has_confirmed_work else "no_published_stops"

    run = db.query(PlanningRun).filter(PlanningRun.id == shift.current_planning_run_id, PlanningRun.status == "applied").first() if shift.current_planning_run_id else None
    if run is None:
        return empty | {"reason": route_refresh_reason()}
    rows = db.query(PlanningItem, Investigation).join(Investigation, Investigation.id == PlanningItem.investigation_id).filter(
        PlanningItem.planning_run_id == run.id, PlanningItem.agent_id == agent.id,
        PlanningItem.outcome == "assigned", Investigation.assigned_agent_id == agent.id,
        Investigation.deleted_at.is_(None), Investigation.latitude.is_not(None),
        Investigation.location_confirmed_at.is_not(None),
    ).order_by(PlanningItem.sequence).all()
    route = db.query(PlanningRoute).filter(PlanningRoute.planning_run_id == run.id, PlanningRoute.agent_id == agent.id).first()
    # A direct override changes the official assignment pointer before route
    # optimization finishes. Never pair those current assignments with stale
    # geometry from the previous applied run.
    planned_case_ids = {
        case_id for (case_id,) in db.query(PlanningItem.investigation_id).filter(
            PlanningItem.planning_run_id == run.id,
            PlanningItem.agent_id == agent.id,
            PlanningItem.outcome == "assigned",
        ).all()
    }
    current_route_case_ids = {case.id for _item, case in rows}
    expected_open_case_ids = {
        case_id for (case_id,) in db.query(Investigation.id).filter(
            Investigation.assigned_agent_id == agent.id,
            Investigation.deleted_at.is_(None),
            Investigation.status.in_(("pending", "assigned")),
            Investigation.region_code == shift.region_code,
            Investigation.location_confirmed_at.is_not(None),
            Investigation.latitude.is_not(None),
            Investigation.longitude.is_not(None),
        ).all()
    }
    route_matches_assignments = (
        current_route_case_ids == planned_case_ids
        and expected_open_case_ids.issubset(current_route_case_ids)
    )
    if not route_matches_assignments:
        return empty | {"reason": route_refresh_reason()}
    return {"work_date": work_date, "shift": shift, "reason": None if rows else "no_published_stops",
        "route": route_response(route, agent, shift) if route and route_matches_assignments else None,
        "stops": [{"service_duration_seconds": case.service_duration_seconds, "investigation_id": case.id, "reference_number": case.reference_number, "address_display": case.address_display,
            "sequence": item.sequence, "estimated_arrival_at": item.estimated_arrival_at, "travel_seconds": item.travel_seconds,
            "travel_metres": item.travel_metres, "latitude": case.latitude, "longitude": case.longitude,
            "priority": case.priority, "status": case.status} for item, case in rows]}


@router.get("/my-route", response_model=AgentRouteResponse)
def get_my_route(work_date: date, db: Session = Depends(get_db), agent: User = Depends(require_roles("agent"))):
    return published_agent_route(db, agent, work_date)


@router.get("/agents/{agent_id}/route", response_model=AgentRouteResponse)
def get_agent_route(agent_id: int, work_date: date, db: Session = Depends(get_db), _: User = Depends(require_roles("admin", "supervisor"))):
    agent = db.query(User).filter(User.id == agent_id, User.role == "agent").first()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return published_agent_route(db, agent, work_date)


@router.get("/agent-shifts", response_model=list[AgentRosterResponse])
def get_agent_shifts(work_date: date, region_code: str | None = None, include_inactive: bool = False, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin", "supervisor"))):
    query = db.query(User).filter(User.role == "agent")
    if actor.role != "admin" or not include_inactive:
        query = query.filter(User.is_active.is_(True))
    agents = query.order_by(User.name).all()
    shifts = {shift.agent_id: shift for shift in db.query(AgentShift).filter(AgentShift.work_date == work_date).all()}
    workloads = dict(db.query(Investigation.assigned_agent_id, func.count(Investigation.id)).filter(
        Investigation.assigned_agent_id.in_([agent.id for agent in agents]),
        Investigation.deleted_at.is_(None),
        Investigation.status.in_(OPEN_STATUSES),
    ).group_by(Investigation.assigned_agent_id).all()) if agents else {}
    visit_workloads = {
        (agent_id, region): count
        for agent_id, region, count in db.query(
            Investigation.assigned_agent_id,
            Investigation.region_code,
            func.count(Investigation.id),
        ).filter(
            Investigation.assigned_agent_id.in_([agent.id for agent in agents]),
            Investigation.deleted_at.is_(None),
            Investigation.status.in_(("pending", "assigned")),
        ).group_by(Investigation.assigned_agent_id, Investigation.region_code).all()
    } if agents else {}
    result = []
    for agent in agents:
        shift = shifts.get(agent.id)
        if region_code and (not shift or shift.region_code != region_code):
            continue
        result.append({"agent": {"id": agent.id, "name": agent.name, "email": agent.email, "role": agent.role, "is_active": agent.is_active},
            "shift": AgentShiftResponse.model_validate(shift) if shift else None,
            "assigned_workload_count": workloads.get(agent.id, 0),
            "visit_workload_count": visit_workloads.get((agent.id, shift.region_code), 0) if shift else 0})
    return result
