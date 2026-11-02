from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.activity import ActivityLog
from app.models.assignment import InvestigationAssignment
from app.models.investigation import Investigation
from app.models.planning import AgentShift, PlanningItem, PlanningRun, PlanningRoute
from app.models.agent_revisit import AgentRevisitRequest
from app.models.agent_schedule import AgentWeeklySchedule, AgentWorkProfile
from app.models.user import User
from app.schemas.planning import (
    AgentShiftInput,
    AgentRouteResponse,
    AgentRosterResponse,
    AgentShiftResponse,
    AgentWorkProfileInput,
    AgentWorkProfileResponse,
    WeeklyScheduleInput,
    WeeklyScheduleResponse,
    AgentAvailabilityResponse,
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
from app.services.locations import catalog
from app.services.planning import (
    OPEN_STATUSES,
    PlanningConflict,
    get_run,
    readiness,
    planning_map_data,
    run_response,
    set_agent_shift,
    route_response_through_last_stop,
    planning_route_overview,
    completed_route_geometry_for_shift,
    planning_dashboard,
    queue_automatic_planning,
    queue_shift_route_refresh,
)
from app.services.planning_status import get_planning_service_status
from app.services.agent_schedules import (
    ALL_REGIONS,
    availability_preview,
    resolve_availability_day,
    enqueue_planning_trigger,
    get_weekly_schedule,
    get_work_profile,
    materialize_work_date,
    save_weekly_schedule,
    save_work_profile,
)
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


@router.get("/agents/{agent_id}/work-profile", response_model=AgentWorkProfileResponse | None)
def read_agent_work_profile(
    agent_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "supervisor")),
):
    if db.query(User.id).filter(User.id == agent_id, User.role == "agent").first() is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return get_work_profile(db, agent_id)


@router.put("/agents/{agent_id}/work-profile", response_model=AgentWorkProfileResponse)
def put_agent_work_profile(
    agent_id: int,
    data: AgentWorkProfileInput,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("admin", "supervisor")),
):
    try:
        profile = save_work_profile(db, agent_id, actor, data)
        today = datetime.now(ZoneInfo("Asia/Manila")).date()
        schedule = get_weekly_schedule(db, agent_id, today)
        if schedule and schedule.enabled:
            from app.services.agent_schedules import materialize_work_date

            materialize_work_date(db, today)
            enqueue_planning_trigger(db, today, schedule.region_code, "agent_depot_updated")
        db.commit()
        db.refresh(profile)
        return profile
    except ValueError as error:
        db.rollback()
        if str(error) == "agent_not_found":
            raise HTTPException(status_code=404, detail="Agent not found") from error
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/agents/{agent_id}/weekly-schedule", response_model=WeeklyScheduleResponse | None)
def read_agent_weekly_schedule(
    agent_id: int,
    on_date: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "supervisor")),
):
    if db.query(User.id).filter(User.id == agent_id, User.role == "agent").first() is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    schedule = get_weekly_schedule(db, agent_id, on_date)
    if schedule is None:
        return None
    return {**{key: getattr(schedule, key) for key in ("id", "agent_id", "effective_from", "effective_until", "enabled", "region_code", "max_visits", "max_open_cases")}, "days": schedule.days}


@router.put("/agents/{agent_id}/weekly-schedule", response_model=WeeklyScheduleResponse)
def put_agent_weekly_schedule(
    agent_id: int,
    data: WeeklyScheduleInput,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("admin", "supervisor")),
):
    try:
        schedule = save_weekly_schedule(db, agent_id, actor, data)
        today = datetime.now(ZoneInfo("Asia/Manila")).date()
        if data.effective_from <= today:
            from app.services.agent_schedules import materialize_work_date

            materialize_work_date(db, today)
            enqueue_planning_trigger(db, today, data.region_code, "weekly_schedule_updated")
        db.commit()
        db.refresh(schedule)
        return {**{key: getattr(schedule, key) for key in ("id", "agent_id", "effective_from", "effective_until", "enabled", "region_code", "max_visits", "max_open_cases")}, "days": schedule.days}
    except ValueError as error:
        db.rollback()
        if str(error) == "agent_not_found":
            raise HTTPException(status_code=404, detail="Agent not found") from error
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/agents/{agent_id}/availability", response_model=AgentAvailabilityResponse)
def read_agent_availability(
    agent_id: int,
    from_date: date,
    to_date: date,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "supervisor")),
):
    if db.query(User.id).filter(User.id == agent_id, User.role == "agent").first() is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        return availability_preview(db, agent_id, from_date, to_date)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


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
    from app.services.agent_schedules import enqueue_planning_trigger

    if work_date == datetime.now(ZoneInfo("Asia/Manila")).date():
        enqueue_planning_trigger(db, work_date, data.region_code, "manual_shift_updated")
    db.commit()
    db.refresh(shift)
    # A shift edit can change eligibility, capacity, or route geometry. Replan
    # all confirmed unassigned work in the affected date and region.
    if work_date == datetime.now(ZoneInfo("Asia/Manila")).date():
        queue_shift_route_refresh(db, agent_id, work_date, actor)
    return shift


@router.delete("/agents/{agent_id}/shifts/{work_date}", status_code=204)
def delete_agent_shift_override(
    agent_id: int,
    work_date: date,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("admin", "supervisor")),
):
    shift = db.query(AgentShift).filter(
        AgentShift.agent_id == agent_id,
        AgentShift.work_date == work_date,
    ).with_for_update().first()
    if shift is None:
        return None
    if shift.source != "manual":
        raise HTTPException(status_code=409, detail="Only a manual shift override can be removed")
    if db.query(User.id).filter(User.id == agent_id, User.role == "agent").first() is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    shift_id = shift.id
    region_code = shift.region_code
    db.delete(shift)
    if work_date == datetime.now(ZoneInfo("Asia/Manila")).date():
        db.flush()
        materialize_work_date(db, work_date)
        restored_shift = db.query(AgentShift).filter(
            AgentShift.agent_id == agent_id,
            AgentShift.work_date == work_date,
        ).first()
        affected_regions = {region_code} if region_code != ALL_REGIONS else {
            code for (code,) in db.query(Investigation.region_code).join(
                InvestigationAssignment,
                InvestigationAssignment.investigation_id == Investigation.id,
            ).filter(
                InvestigationAssignment.agent_id == agent_id,
                InvestigationAssignment.is_active.is_(True),
                InvestigationAssignment.assignment_source == "automatic",
                Investigation.status.in_(("pending", "assigned")),
                Investigation.deleted_at.is_(None),
            ).distinct().all() if code
        }
        if restored_shift is not None and restored_shift.is_available:
            affected_regions.add(restored_shift.region_code)
        for affected_region in affected_regions:
            enqueue_planning_trigger(db, work_date, affected_region, "manual_shift_override_removed")
    db.add(ActivityLog(actor_id=actor.id, action="agent.shift_override_removed", object_type="agent_shift", object_id=shift_id, details={"agent_id": agent_id, "work_date": str(work_date)}))
    db.commit()
    return None


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
    completed_route_geometry = completed_route_geometry_for_shift(db, shift)
    cancelled_investigations = [
        {
            "id": case.id,
            "reference_number": case.reference_number,
            "address_display": case.address_display,
            "status": case.status,
            "reopen_on": case.reopen_on,
            "priority": case.priority,
            "region_code": case.region_code,
            "latitude": case.latitude,
            "longitude": case.longitude,
        }
        for case in db.query(Investigation).filter(
            Investigation.assigned_agent_id == agent.id,
            Investigation.deleted_at.is_(None),
            Investigation.status == "cancelled",
            Investigation.reopen_on == work_date + timedelta(days=1),
        ).order_by(Investigation.id).all()
    ]
    revisit_requests = [
        {
            "id": request.id,
            "investigation_id": request.investigation_id,
            "reference_number": reference_number,
            "report_id": request.report_id,
            "agent_id": request.agent_id,
            "target_work_date": request.target_work_date,
            "status": request.status,
            "planning_run_id": request.planning_run_id,
            "created_at": request.created_at,
            "completed_at": request.completed_at,
        }
        for request, reference_number in db.query(
            AgentRevisitRequest, Investigation.reference_number,
        ).join(Investigation, Investigation.id == AgentRevisitRequest.investigation_id).filter(
            AgentRevisitRequest.agent_id == agent.id,
            AgentRevisitRequest.status.in_(("waiting_for_shift", "queued", "routed")),
        ).order_by(AgentRevisitRequest.created_at, AgentRevisitRequest.id).all()
    ]
    empty = {
        "work_date": work_date,
        "shift": shift,
        "route": None,
        "completed_route_geometry": completed_route_geometry,
        "stops": [],
        "cancelled_investigations": cancelled_investigations,
        "revisit_requests": revisit_requests,
    }
    if shift is None:
        return empty | {"reason": "no_shift"}
    if not shift.is_available:
        return empty | {"reason": "shift_unavailable"}

    def assigned_stop_placeholders() -> list[dict]:
        """Keep current assignments visible when there is no current route."""
        query = db.query(Investigation).filter(
            Investigation.assigned_agent_id == agent.id,
            Investigation.deleted_at.is_(None),
            Investigation.status.in_(("pending", "assigned")),
            Investigation.location_confirmed_at.is_not(None),
            Investigation.latitude.is_not(None),
            Investigation.longitude.is_not(None),
        )
        if shift.region_code == ALL_REGIONS:
            query = query.filter(Investigation.region_code.in_(catalog()["region_codes"]))
        else:
            query = query.filter(Investigation.region_code == shift.region_code)
        cases = query.order_by(Investigation.created_at, Investigation.id).all()
        return [
            {
                "service_duration_seconds": case.service_duration_seconds,
                "investigation_id": case.id,
                "reference_number": case.reference_number,
                "address_display": case.address_display,
                "sequence": None,
                "estimated_arrival_at": None,
                "estimated_service_start_at": None,
                "waiting_seconds": None,
                "travel_seconds": None,
                "travel_metres": None,
                "latitude": case.latitude,
                "longitude": case.longitude,
                "priority": case.priority,
                "status": case.status,
            }
            for case in cases
        ]

    def route_refresh_reason() -> str:
        auto_runs = db.query(PlanningRun).filter(
            PlanningRun.work_date == work_date,
            PlanningRun.region_code.in_((shift.region_code, ALL_REGIONS)),
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
            Investigation.region_code.in_(catalog()["region_codes"])
            if shift.region_code == ALL_REGIONS
            else Investigation.region_code == shift.region_code,
            Investigation.location_confirmed_at.is_not(None),
            Investigation.latitude.is_not(None),
            Investigation.longitude.is_not(None),
        ).first() is not None
        return "route_needs_refresh" if has_confirmed_work else "no_published_stops"

    run = db.query(PlanningRun).filter(PlanningRun.id == shift.current_planning_run_id, PlanningRun.status == "applied").first() if shift.current_planning_run_id else None
    if run is None:
        return empty | {
            "reason": route_refresh_reason(),
            "stops": assigned_stop_placeholders(),
        }
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
        return empty | {
            "reason": route_refresh_reason(),
            "stops": assigned_stop_placeholders(),
        }
    return {"work_date": work_date, "shift": shift, "reason": None if rows else "no_published_stops",
        "route": route_response_through_last_stop(route, agent, shift, rows) if route and route_matches_assignments else None,
        "completed_route_geometry": completed_route_geometry,
        "revisit_requests": revisit_requests,
        "cancelled_investigations": cancelled_investigations,
        "stops": [{"service_duration_seconds": case.service_duration_seconds, "investigation_id": case.id, "reference_number": case.reference_number, "address_display": case.address_display,
            "sequence": item.sequence, "estimated_arrival_at": item.estimated_arrival_at,
            "estimated_service_start_at": item.estimated_service_start_at, "waiting_seconds": item.waiting_seconds,
            "travel_seconds": item.travel_seconds,
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
        schedule = get_weekly_schedule(db, agent.id, work_date)
        availability_day = resolve_availability_day(db, agent.id, work_date)
        if region_code and (not shift or shift.region_code not in {region_code, ALL_REGIONS}) and (not schedule or not schedule.enabled or schedule.region_code not in {region_code, ALL_REGIONS}):
            continue
        result.append({"agent": {"id": agent.id, "name": agent.name, "email": agent.email, "role": agent.role, "is_active": agent.is_active},
            "shift": AgentShiftResponse.model_validate(shift) if shift else None,
            "assigned_workload_count": workloads.get(agent.id, 0),
            "visit_workload_count": visit_workloads.get((agent.id, shift.region_code), 0) if shift and shift.region_code != ALL_REGIONS else workloads.get(agent.id, 0),
            "schedule_enabled": bool(schedule and schedule.enabled),
            "work_profile_set": bool(get_work_profile(db, agent.id) and get_work_profile(db, agent.id).depot_latitude is not None),
            "availability_day": availability_day})
    return result
