from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from math import isfinite
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import h3

from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session, joinedload

from app.config.settings import OSRM_DATASET_VERSION, PLANNING_MAX_LOCATIONS
from app.models.activity import ActivityLog
from app.models.assignment import InvestigationAssignment
from app.models.investigation import Investigation
from app.models.planning import AgentShift, PlanningItem, PlanningRun, PlanningRoute
from app.models.user import User
from app.schemas.planning import LockedAssignment, PlanningRunCreate
from app.services.geospatial import cells_for_point
from app.services.locations import catalog
from app.services.routing import OSRMClient, RoutingUnavailable, VROOMClient, valid_route_geometry


OPEN_STATUSES = ("assigned", "in_progress", "under_review", "returned_for_correction")
PRIORITY_VALUES = {"normal": 10, "high": 50, "urgent": 100}
logger = logging.getLogger("app.planning")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    planning_log_handler = logging.StreamHandler()
    planning_log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(planning_log_handler)


class PlanningConflict(ValueError):
    pass


def _log_planning_event(event: str, **fields) -> None:
    """Write aggregate planning signals without investigation or location data."""
    logger.info("planning_event %s", json.dumps({"event": event, **fields}, sort_keys=True, default=str))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _epoch(value: datetime) -> int:
    return int(_as_utc(value).timestamp())


def _iso_utc(value: datetime | None) -> str | None:
    return _as_utc(value).isoformat() if value is not None else None


def _digest(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def clear_published_routes(db: Session, planning_run_ids, agent_ids=None) -> None:
    query = db.query(AgentShift).filter(
        AgentShift.current_planning_run_id.in_(planning_run_ids)
    )
    if agent_ids is not None:
        agent_ids = sorted(set(agent_ids))
        if not agent_ids:
            return
        query = query.filter(AgentShift.agent_id.in_(agent_ids))
    shifts = query.order_by(AgentShift.agent_id).with_for_update().all()
    for shift in shifts:
        shift.current_planning_run_id = None


def planned_agent_ids_for_investigation(db: Session, investigation_id: int) -> list[int]:
    return [
        agent_id
        for (agent_id,) in db.query(PlanningItem.agent_id)
        .filter(
            PlanningItem.investigation_id == investigation_id,
            PlanningItem.agent_id.is_not(None),
        )
        .distinct()
        .all()
    ]


def set_agent_shift(db: Session, agent_id: int, values, commit: bool = True) -> AgentShift:
    region_codes = catalog()["region_codes"]
    if values.region_code not in region_codes:
        raise PlanningConflict("invalid_region")
    manila = ZoneInfo("Asia/Manila")
    if values.shift_starts_at.astimezone(manila).date() != values.work_date or values.shift_ends_at.astimezone(manila).date() != values.work_date:
        raise PlanningConflict("shift_must_match_work_date")

    shift = (
        db.query(AgentShift)
        .filter(AgentShift.agent_id == agent_id, AgentShift.work_date == values.work_date)
        .with_for_update()
        .first()
    )
    agent = db.query(User).filter(User.id == agent_id).with_for_update().first()
    if agent is None or agent.role != "agent":
        raise PlanningConflict("agent_not_found")
    if shift is None:
        shift = AgentShift(agent_id=agent_id, work_date=values.work_date)
        db.add(shift)

    for field in (
        "region_code", "is_available", "start_latitude", "start_longitude",
        "end_latitude", "end_longitude", "max_visits", "max_open_cases",
        "start_location_label", "start_location_source", "start_location_provider_ref",
        "end_location_label", "end_location_source", "end_location_provider_ref",
    ):
        setattr(shift, field, getattr(values, field))
    shift.shift_starts_at = _as_utc(values.shift_starts_at)
    shift.shift_ends_at = _as_utc(values.shift_ends_at)
    # A changed shift must not keep publishing a route computed for old inputs.
    shift.current_planning_run_id = None

    ready_runs = db.query(PlanningRun).filter(
        PlanningRun.work_date == values.work_date,
        PlanningRun.status.in_(("queued", "running", "ready")),
    ).all()
    for run in ready_runs:
        if agent_id in run.agent_ids:
            run.status = "stale"
            run.error_code = "shift_changed"

    if commit:
        db.commit()
        db.refresh(shift)
    return shift


def readiness(db: Session, work_date: date, region_code: str, resolution: int) -> dict:
    if resolution not in (7, 8, 9):
        raise PlanningConflict("invalid_h3_resolution")
    if region_code not in catalog()["region_codes"]:
        raise PlanningConflict("invalid_region")

    cases = (
        db.query(Investigation)
        .options(joinedload(Investigation.assigned_agent))
        .filter(
            Investigation.deleted_at.is_(None),
            Investigation.region_code == region_code,
            Investigation.status.in_(("pending", "assigned")),
        )
        .order_by(Investigation.created_at.asc())
        .all()
    )
    available_shifts = (
        db.query(AgentShift, User)
        .join(User, User.id == AgentShift.agent_id)
        .filter(
            AgentShift.work_date == work_date,
            AgentShift.region_code == region_code,
            AgentShift.is_available.is_(True),
            User.role == "agent",
            User.is_active.is_(True),
        )
        .order_by(User.name)
        .all()
    )
    active_agent_count = (
        db.query(func.count(User.id))
        .filter(User.role == "agent", User.is_active.is_(True))
        .scalar()
        or 0
    )

    eligible_cases = []
    excluded_cases = []
    cell_counts: dict[str, int] = {}
    for case in cases:
        reason = None
        if not case.location_confirmed:
            reason = "location_unconfirmed"
        if reason:
            excluded_cases.append({
                "id": case.id,
                "reference_number": case.reference_number,
                "reason": reason,
                "assigned_agent_id": case.assigned_agent_id,
                "assigned_agent_name": case.assigned_agent_name,
            })
            continue
        cell = getattr(case, f"h3_r{resolution}") or cells_for_point(case.latitude, case.longitude)[f"h3_r{resolution}"]
        cell_counts[cell] = cell_counts.get(cell, 0) + 1
        eligible_cases.append({
            "id": case.id,
            "reference_number": case.reference_number,
            "status": case.status,
            "priority": case.priority,
            "address_display": case.address_display,
            "service_duration_seconds": case.service_duration_seconds,
            "location_confirmed": True,
            "latitude": case.latitude,
            "longitude": case.longitude,
            "assigned_agent_id": case.assigned_agent_id,
            "assigned_agent_name": case.assigned_agent_name,
        })

    agent_ids = [agent.id for _, agent in available_shifts]
    open_case_counts = dict(
        db.query(Investigation.assigned_agent_id, func.count(Investigation.id))
        .filter(
            Investigation.assigned_agent_id.in_(agent_ids),
            Investigation.deleted_at.is_(None),
            Investigation.status.in_(OPEN_STATUSES),
        )
        .group_by(Investigation.assigned_agent_id)
        .all()
    ) if agent_ids else {}

    agents = []
    for shift, agent in available_shifts:
        open_count = int(open_case_counts.get(agent.id, 0))
        agents.append({
            "id": agent.id,
            "name": agent.name,
            "region_code": shift.region_code,
            "shift_id": shift.id,
            "start": _shift_point(shift, "start"),
            "end": _shift_point(shift, "end"),
            "shift_starts_at": _as_utc(shift.shift_starts_at),
            "shift_ends_at": _as_utc(shift.shift_ends_at),
            "max_visits": shift.max_visits,
            "max_open_cases": shift.max_open_cases,
            "open_case_count": open_count,
            "current_planning_run_id": shift.current_planning_run_id,
        })

    return {
        "work_date": work_date,
        "region_code": region_code,
        "resolution": resolution,
        "active_agent_count": active_agent_count,
        "unavailable_agent_count": max(active_agent_count - len(available_shifts), 0),
        "eligible_cases": eligible_cases,
        "available_agents": agents,
        "excluded_cases": excluded_cases,
        "density": [{"cell": cell, "count": count, "geometry": _cell_polygon(cell)} for cell, count in sorted(cell_counts.items())],
    }


def planning_map_data(db: Session, work_date: date, region_code: str | None = None) -> dict:
    """Return map visibility data independently from plan eligibility/readiness."""
    if region_code and region_code not in catalog()["region_codes"]:
        raise PlanningConflict("invalid_region")

    investigations_query = db.query(Investigation).options(
        joinedload(Investigation.assigned_agent),
    ).filter(
        Investigation.deleted_at.is_(None),
    )
    if region_code:
        investigations_query = investigations_query.filter(Investigation.region_code == region_code)
    all_investigations = investigations_query.order_by(Investigation.id).all()
    located_investigations = [
        case for case in all_investigations
        if case.location_confirmed and case.latitude is not None and case.longitude is not None
    ]
    unlocated_investigations = [
        {
            "id": case.id,
            "reference_number": case.reference_number,
            "status": case.status,
            "region_code": case.region_code,
        }
        for case in all_investigations
        if not (case.location_confirmed and case.latitude is not None and case.longitude is not None)
    ]

    shift_join = and_(
        AgentShift.agent_id == User.id,
        AgentShift.work_date == work_date,
    )
    if region_code:
        shift_join = and_(shift_join, AgentShift.region_code == region_code)
    agent_query = db.query(User, AgentShift).filter(User.role == "agent")
    agent_query = agent_query.join(AgentShift, shift_join) if region_code else agent_query.outerjoin(AgentShift, shift_join)
    agent_rows = agent_query.order_by(User.name, User.id).all()
    agents = []
    unlocated_agents = []
    for agent, shift in agent_rows:
        has_start = bool(shift and shift.start_latitude is not None and shift.start_longitude is not None)
        agents.append({
            "id": agent.id,
            "name": agent.name,
            "is_active": agent.is_active,
            "region_code": shift.region_code if shift else None,
            "is_available": shift.is_available if shift else None,
            "shift_starts_at": _as_utc(shift.shift_starts_at) if shift else None,
            "shift_ends_at": _as_utc(shift.shift_ends_at) if shift else None,
            "start": _shift_point(shift, "start") if has_start else None,
        })
        if not has_start:
            unlocated_agents.append({"id": agent.id, "name": agent.name, "is_active": agent.is_active})

    return {
        "work_date": work_date,
        "region_code": region_code,
        "investigations": [
            {
                "id": case.id,
                "reference_number": case.reference_number,
                "address_display": case.address_display,
                "latitude": case.latitude,
                "longitude": case.longitude,
                "priority": case.priority,
                "status": case.status,
                "region_code": case.region_code,
                "assigned_agent_id": case.assigned_agent_id,
                "assigned_agent_name": case.assigned_agent_name,
                "service_duration_seconds": case.service_duration_seconds,
                "visit_not_before_at": case.visit_not_before_at,
                "visit_due_at": case.visit_due_at,
            }
            for case in located_investigations
        ],
        "agents": agents,
        "unlocated_investigations": unlocated_investigations,
        "unlocated_agents": unlocated_agents,
    }


def _shift_point(shift: AgentShift, prefix: str) -> dict | None:
    latitude = getattr(shift, f"{prefix}_latitude")
    if latitude is None:
        return None
    return {"latitude": latitude, "longitude": getattr(shift, f"{prefix}_longitude"), "label": getattr(shift, f"{prefix}_location_label")}


def _cell_polygon(cell: str) -> dict:
    ring = [[longitude, latitude] for latitude, longitude in h3.cell_to_boundary(cell)]
    return {"type": "Polygon", "coordinates": [ring + [ring[0]]]}


def _build_route_geometries(osrm, case_rows, shifts, outcomes) -> list[dict]:
    cases = {case.id: case for case in case_rows}
    routes = []
    for shift in shifts:
        stops = sorted([item for item in outcomes.values() if item.get("agent_id") == shift.agent_id and item.get("outcome") == "assigned"], key=lambda item: item["sequence"])
        if not stops:
            continue
        coordinates = [(shift.start_latitude, shift.start_longitude)]
        coordinates.extend((cases[item["investigation_id"]].latitude, cases[item["investigation_id"]].longitude) for item in stops)
        if shift.end_latitude is not None:
            coordinates.append((shift.end_latitude, shift.end_longitude))
        route = {"agent_id": shift.agent_id, "start": _shift_point(shift, "start"), "end": _shift_point(shift, "end"), "geometry_status": "failed", "geometry_error_code": None, "geometry": None, "geometry_digest": None, "total_distance_metres": None, "total_travel_seconds": None}
        try:
            result = osrm.route(coordinates)
            route.update(geometry_status="ready", geometry=result["geometry"], geometry_digest=_digest(result["geometry"]), total_distance_metres=round(result["distance"]), total_travel_seconds=round(result["duration"]))
        except RoutingUnavailable as error:
            route["geometry_error_code"] = str(error)
        routes.append(route)
    return routes


def route_response(route: PlanningRoute, agent: User, shift: AgentShift | None = None) -> dict:
    response = {key: getattr(route, key) for key in ("agent_id", "geometry_status", "geometry_error_code", "geometry", "geometry_digest", "total_distance_metres", "total_travel_seconds", "start", "end")} | {"agent_name": agent.name, "shift": shift}
    if not _route_geometry_ready(route):
        response.update(geometry_status="failed", geometry_error_code=route.geometry_error_code or "route_geometry_invalid", geometry=None, geometry_digest=None, total_distance_metres=None, total_travel_seconds=None)
    return response


def _route_geometry_ready(route: PlanningRoute) -> bool:
    return bool(
        route.geometry_status == "ready" and valid_route_geometry(route.geometry)
        and route.geometry_digest and _digest(route.geometry) == route.geometry_digest
    )


def planning_route_overview(db: Session, work_date: date, region_code: str | None = None) -> dict:
    """Return current assignment-driven routes, never a route for a stale stop set."""
    if region_code and region_code not in catalog()["region_codes"]:
        raise PlanningConflict("invalid_region")

    query = db.query(User, AgentShift).outerjoin(
        AgentShift,
        and_(AgentShift.agent_id == User.id, AgentShift.work_date == work_date),
    ).filter(User.role == "agent")
    if region_code:
        query = query.filter(AgentShift.region_code == region_code)
    agent_rows = query.order_by(User.name, User.id).all()
    agents = [agent for agent, _shift in agent_rows]
    agent_ids = [agent.id for agent in agents]
    shifts = {shift.agent_id: shift for _agent, shift in agent_rows if shift is not None}
    open_counts = dict(db.query(Investigation.assigned_agent_id, func.count(Investigation.id)).filter(
        Investigation.assigned_agent_id.in_(agent_ids),
        Investigation.deleted_at.is_(None),
        Investigation.status.in_(OPEN_STATUSES),
    ).group_by(Investigation.assigned_agent_id).all()) if agent_ids else {}

    auto_runs = db.query(PlanningRun).filter(
        PlanningRun.work_date == work_date,
        PlanningRun.auto_publish.is_(True),
        PlanningRun.status.in_(("queued", "running", "ready", "failed", "applied")),
    ).order_by(PlanningRun.created_at.desc(), PlanningRun.id.desc()).all()
    if region_code:
        auto_runs = [run for run in auto_runs if run.region_code == region_code]
    latest_auto_run_by_agent = {}
    for run in auto_runs:
        for agent_id in run.agent_ids or []:
            if agent_id in agent_ids and agent_id not in latest_auto_run_by_agent:
                latest_auto_run_by_agent[agent_id] = run

    cases = db.query(Investigation).filter(
        Investigation.assigned_agent_id.in_(agent_ids),
        Investigation.deleted_at.is_(None),
        Investigation.status.in_(("pending", "assigned")),
        Investigation.location_confirmed_at.is_not(None),
        Investigation.latitude.is_not(None),
        Investigation.longitude.is_not(None),
    ).order_by(Investigation.id).all() if agent_ids else []
    current_ids_by_agent: dict[int, set[int]] = {agent_id: set() for agent_id in agent_ids}
    for case in cases:
        shift = shifts.get(case.assigned_agent_id)
        if shift is not None and shift.is_available and shift.region_code == case.region_code:
            current_ids_by_agent[case.assigned_agent_id].add(case.id)

    active_assignments = db.query(InvestigationAssignment).filter(
        InvestigationAssignment.is_active.is_(True),
        InvestigationAssignment.auto_route_work_date == work_date,
        InvestigationAssignment.auto_route_status.is_not(None),
    ).order_by(InvestigationAssignment.assigned_at.desc(), InvestigationAssignment.id.desc()).all()
    latest_refresh_by_agent: dict[int, InvestigationAssignment] = {}
    for assignment in active_assignments:
        for agent_id in assignment.auto_route_agent_ids or [assignment.agent_id]:
            if agent_id in agent_ids and agent_id not in latest_refresh_by_agent:
                latest_refresh_by_agent[agent_id] = assignment

    run_ids = sorted({shift.current_planning_run_id for shift in shifts.values() if shift.current_planning_run_id})
    runs = {
        run.id: run
        for run in db.query(PlanningRun).filter(
            PlanningRun.id.in_(run_ids),
            PlanningRun.work_date == work_date,
            PlanningRun.status == "applied",
        ).all()
    } if run_ids else {}
    published_run_ids = sorted(runs)
    route_rows = db.query(PlanningRoute, User).join(
        User, User.id == PlanningRoute.agent_id,
    ).filter(PlanningRoute.planning_run_id.in_(published_run_ids)).all() if published_run_ids else []
    route_by_run_agent = {(route.planning_run_id, route.agent_id): (route, agent) for route, agent in route_rows}
    item_rows = db.query(PlanningItem, Investigation).join(
        Investigation, Investigation.id == PlanningItem.investigation_id,
    ).filter(
        PlanningItem.planning_run_id.in_(published_run_ids),
        PlanningItem.outcome == "assigned",
        PlanningItem.agent_id.in_(agent_ids),
    ).all() if published_run_ids and agent_ids else []
    items_by_run_agent: dict[tuple[int, int], list[tuple[PlanningItem, Investigation]]] = {}
    for item, case in item_rows:
        items_by_run_agent.setdefault((item.planning_run_id, item.agent_id), []).append((item, case))

    overview_agents = []
    for agent, _shift in agent_rows:
        shift = shifts.get(agent.id)
        refresh = latest_refresh_by_agent.get(agent.id)
        planning_run = latest_auto_run_by_agent.get(agent.id)
        run_id = shift.current_planning_run_id if shift else None
        run = runs.get(run_id) if run_id else None
        pair = route_by_run_agent.get((run_id, agent.id)) if run_id else None
        route_model, route_agent = pair if pair else (None, None)
        route_items = items_by_run_agent.get((run_id, agent.id), []) if run_id else []
        stored_case_ids = {case.id for _item, case in route_items}
        route_case_ids = {
            case.id for _item, case in route_items
            if case.assigned_agent_id == agent.id
        }
        expected_case_ids = current_ids_by_agent.get(agent.id, set())
        exact_current_route = bool(
            shift
            and shift.is_available
            and run
            and route_model
            and route_case_ids == stored_case_ids
            and expected_case_ids.issubset(route_case_ids)
        )

        route = None
        stops = []
        if exact_current_route and route_model and route_agent and shift:
            route = route_response(route_model, route_agent, shift)
            stops = [
                {
                    "service_duration_seconds": case.service_duration_seconds,
                    "investigation_id": case.id,
                    "reference_number": case.reference_number,
                    "address_display": case.address_display,
                    "sequence": item.sequence,
                    "estimated_arrival_at": item.estimated_arrival_at,
                    "travel_seconds": item.travel_seconds,
                    "travel_metres": item.travel_metres,
                    "latitude": case.latitude,
                    "longitude": case.longitude,
                    "priority": case.priority,
                    "status": case.status,
                }
                for item, case in sorted(route_items, key=lambda row: (row[0].sequence or 0, row[1].id))
            ]

        if route is not None and route["geometry_status"] == "ready":
            route_status = "published"
        elif route is not None:
            route_status = "failed"
        elif refresh is not None and refresh.auto_route_status in {
            "queued", "running", "failed", "partially_published",
        }:
            route_status = refresh.auto_route_status
        elif planning_run and planning_run.status in {"queued", "running", "ready"}:
            route_status = "queued" if planning_run.status == "queued" else "running"
        elif planning_run and planning_run.status == "failed":
            route_status = "failed"
        elif expected_case_ids:
            route_status = "needs_refresh"
        else:
            route_status = "none"

        refresh_errors = list(refresh.auto_route_errors or []) if refresh else []
        if route and route.get("geometry_error_code"):
            refresh_errors.append(route["geometry_error_code"])

        overview_agents.append({
            "id": agent.id,
            "name": agent.name,
            "is_active": agent.is_active,
            "region_code": shift.region_code if shift else None,
            "shift": shift,
            "route_status": route_status,
            "refresh_errors": list(dict.fromkeys(refresh_errors)),
            "refresh_investigation_id": refresh.investigation_id if refresh else None,
            "run_id": run.id if run else None,
            "planning_status": (
                "queued" if planning_run and planning_run.status == "queued"
                else "running" if planning_run and planning_run.status in {"running", "ready"}
                else "failed" if planning_run and planning_run.status == "failed" and route is None
                else "idle"
            ),
            "planning_error_code": planning_run.error_code if planning_run and planning_run.status == "failed" else None,
            "planning_run_id": planning_run.id if planning_run else None,
            "open_case_count": int(open_counts.get(agent.id, 0)),
            "remaining_open_capacity": max(0, shift.max_open_cases - int(open_counts.get(agent.id, 0))) if shift else None,
            "route": route,
            "stops": stops,
        })

    return {"work_date": work_date, "region_code": region_code, "agents": overview_agents}


def planning_dashboard(db: Session, work_date: date, region_code: str | None = None) -> dict:
    if region_code and region_code not in catalog()["region_codes"]:
        raise PlanningConflict("invalid_region")

    cases_query = db.query(Investigation).filter(Investigation.deleted_at.is_(None))
    if region_code:
        cases_query = cases_query.filter(Investigation.region_code == region_code)
    cases = cases_query.order_by(Investigation.id).all()
    case_ids = [case.id for case in cases]
    active_assignments = db.query(InvestigationAssignment).filter(
        InvestigationAssignment.investigation_id.in_(case_ids),
        InvestigationAssignment.is_active.is_(True),
    ).all() if case_ids else []
    assignment_by_case = {item.investigation_id: item for item in active_assignments}

    runs_query = db.query(PlanningRun).filter(
        PlanningRun.work_date == work_date,
        PlanningRun.auto_publish.is_(True),
    )
    if region_code:
        runs_query = runs_query.filter(PlanningRun.region_code == region_code)
    runs = runs_query.order_by(PlanningRun.created_at.desc(), PlanningRun.id.desc()).all()
    run_by_id = {run.id: run for run in runs}
    latest_run_by_case = {}
    for run in runs:
        for case_id in run.investigation_ids or []:
            if case_id in case_ids and case_id not in latest_run_by_case:
                latest_run_by_case[case_id] = run
    items = db.query(PlanningItem).filter(
        PlanningItem.planning_run_id.in_(run_by_id),
        PlanningItem.investigation_id.in_(case_ids),
    ).order_by(PlanningItem.planning_run_id.desc()).all() if run_by_id and case_ids else []
    item_by_run_case = {}
    for item in items:
        item_by_run_case.setdefault((item.planning_run_id, item.investigation_id), item)

    investigation_states = []
    for case in cases:
        assignment = assignment_by_case.get(case.id)
        run = latest_run_by_case.get(case.id)
        item = item_by_run_case.get((run.id, case.id)) if run else None
        if case.assigned_agent_id is not None:
            state, reason = "assigned", None
        elif not case.location_confirmed:
            state, reason = "pending", "location_unconfirmed"
        elif run and run.status in {"queued", "running", "ready"}:
            state, reason = "optimizing", None
        elif run and run.status == "failed":
            state, reason = "failed", run.error_code or "optimization_failed"
        elif run and run.status == "applied" and item and item.outcome == "unassigned":
            state, reason = "unassigned", item.reason
        else:
            state, reason = "pending", None
        investigation_states.append({
            "investigation_id": case.id,
            "planning_status": state,
            "reason": reason,
            "planning_run_id": run.id if run else None,
            "assignment_source": assignment.assignment_source if assignment else None,
        })

    active_agents_query = db.query(User, AgentShift).outerjoin(
        AgentShift,
        and_(AgentShift.agent_id == User.id, AgentShift.work_date == work_date),
    ).filter(User.role == "agent", User.is_active.is_(True))
    if region_code:
        active_agents_query = active_agents_query.filter(AgentShift.region_code == region_code)
    agent_rows = active_agents_query.all()
    available_agents = sum(1 for _agent, shift in agent_rows if shift and shift.is_available)
    active_runs = [run for run in runs if run.status in {"queued", "running", "ready"}]
    overview = planning_route_overview(db, work_date, region_code)
    published_routes = sum(
        1
        for agent in overview["agents"]
        if agent["route_status"] == "published" and agent["route"] is not None
    )
    return {
        "work_date": work_date,
        "region_code": region_code,
        "total_investigations": len(cases),
        "automatically_assigned": sum(1 for item in active_assignments if item.assignment_source == "automatic"),
        "unassigned_investigations": sum(
            1 for case in cases
            if case.assigned_agent_id is None and case.status in {"pending", "assigned"}
        ),
        "active_agents": len(agent_rows),
        "available_agents": available_agents,
        "optimizing_routes": sum(max(1, len(run.agent_ids or [])) for run in active_runs),
        "published_routes": published_routes,
        "failed_planning_jobs": sum(1 for run in runs if run.status == "failed"),
        "investigation_states": investigation_states,
    }


def _geometry_complete(db: Session, run_id: int, assigned_agents: set[int]) -> bool:
    routes = db.query(PlanningRoute).filter(PlanningRoute.planning_run_id == run_id).all()
    valid = {route.agent_id for route in routes if _route_geometry_ready(route)}
    return assigned_agents.issubset(valid)


def create_run(
    db: Session,
    request,
    requester: User,
    commit: bool = True,
) -> PlanningRun:
    if request.region_code not in catalog()["region_codes"]:
        raise PlanningConflict("invalid_region")
    shifts = (
        db.query(AgentShift)
        .filter(
            AgentShift.agent_id.in_(request.agent_ids),
            AgentShift.work_date == request.work_date,
        )
        .all()
    )
    shift_by_agent = {shift.agent_id: shift for shift in shifts}
    agents = db.query(User).filter(User.id.in_(request.agent_ids)).order_by(User.id).all()
    agent_by_id = {agent.id: agent for agent in agents}
    if len(agents) != len(request.agent_ids):
        raise PlanningConflict("agent_not_found")
    for agent_id in request.agent_ids:
        shift = shift_by_agent.get(agent_id)
        agent = agent_by_id[agent_id]
        if agent.role != "agent" or not agent.is_active:
            raise PlanningConflict("agent_not_eligible")
        if shift is None or not shift.is_available:
            raise PlanningConflict("agent_shift_unavailable")
        if shift.region_code != request.region_code:
            raise PlanningConflict("agent_region_mismatch")
    case_ids = set(request.investigation_ids)
    locked = {item.investigation_id: item.agent_id for item in request.locked_assignments}
    if any(agent_id not in request.agent_ids for agent_id in locked.values()):
        raise PlanningConflict("locked_agent_not_selected")

    # A replacement run for an agent/date always carries forward the current stops.
    for shift in shifts:
        if shift.current_planning_run_id is None:
            continue
        old_items = (
            db.query(PlanningItem, Investigation.status)
            .join(Investigation, Investigation.id == PlanningItem.investigation_id)
            .filter(
                PlanningItem.planning_run_id == shift.current_planning_run_id,
                PlanningItem.agent_id == shift.agent_id,
                PlanningItem.outcome == "assigned",
                Investigation.deleted_at.is_(None),
                Investigation.status.in_(("pending", "assigned")),
            )
            .all()
        )
        for item, _status in old_items:
            case_ids.add(item.investigation_id)
            locked[item.investigation_id] = shift.agent_id

    if len(case_ids) > 80:
        raise PlanningConflict("run_too_large")
    cases = db.query(Investigation).filter(Investigation.id.in_(sorted(case_ids))).order_by(Investigation.id).all()
    if len(cases) != len(case_ids):
        raise PlanningConflict("investigation_not_found")
    case_coordinates = set()
    for case in cases:
        if case.deleted_at is not None or case.status not in {"pending", "assigned"}:
            raise PlanningConflict("investigation_not_assignable")
        if case.region_code != request.region_code:
            raise PlanningConflict("investigation_region_mismatch")
        if not case.location_confirmed:
            raise PlanningConflict("location_unconfirmed")
        fixed_agent = locked.get(case.id) or case.assigned_agent_id
        if fixed_agent is not None and fixed_agent not in request.agent_ids:
            raise PlanningConflict("locked_agent_not_selected")
        case_coordinates.add((round(case.latitude, 6), round(case.longitude, 6)))
    for shift in shifts:
        case_coordinates.add((round(shift.start_latitude, 6), round(shift.start_longitude, 6)))
        if shift.end_latitude is not None:
            case_coordinates.add((round(shift.end_latitude, 6), round(shift.end_longitude, 6)))
    if len(case_coordinates) > min(80, PLANNING_MAX_LOCATIONS):
        raise PlanningConflict("run_too_large")

    run = PlanningRun(
        requested_by_id=requester.id,
        work_date=request.work_date,
        region_code=request.region_code,
        investigation_ids=sorted(case_ids),
        agent_ids=request.agent_ids,
        locked_assignments=[{"investigation_id": key, "agent_id": value} for key, value in sorted(locked.items())],
        status="queued",
    )
    db.add(run)
    run.input_digest = _digest(_snapshot(db, run, cases, shifts, agents))
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(run)
    _log_planning_event(
        "planning.run_queued",
        planning_run_id=run.id,
        work_date=run.work_date.isoformat(),
        region_code=run.region_code,
        investigation_count=len(case_ids),
        agent_count=len(run.agent_ids),
        locked_assignment_count=len(run.locked_assignments),
        unique_location_count=len(case_coordinates),
    )
    return run


def _link_auto_route_run(db: Session, run: PlanningRun) -> None:
    assignment_ids = run.auto_assignment_ids or ([run.auto_assignment_id] if run.auto_assignment_id else [])
    for assignment_id in assignment_ids:
        assignment = db.get(InvestigationAssignment, assignment_id)
        if assignment is None:
            continue
        assignment.auto_route_work_date = run.work_date
        assignment.auto_route_run_ids = list(dict.fromkeys([*(assignment.auto_route_run_ids or []), run.id]))
        assignment.auto_route_agent_ids = list(dict.fromkeys([*(assignment.auto_route_agent_ids or []), *(run.agent_ids or [])]))
        if run.status == "failed":
            assignment.auto_route_errors = list(dict.fromkeys([*(assignment.auto_route_errors or []), run.error_code or "automatic_planning_failed"]))
            assignment.auto_route_status = "failed"
        else:
            assignment.auto_route_status = "queued"


def queue_automatic_planning(
    db: Session,
    region_code: str,
    requester: User,
    work_date: date | None = None,
    *,
    auto_assignment_id: int | None = None,
    auto_assignment_ids: list[int] | None = None,
    exclude_investigation_ids: set[int] | None = None,
) -> PlanningRun | None:
    """Coalesce a regional planning trigger and enqueue one VROOM run.

    Existing assignments are carried into the run as locked jobs. Only confirmed,
    unassigned pending cases are offered for new assignment. H3 is used to order
    the bounded batch geographically; OSRM/VROOM remain responsible for routes
    and agent selection.
    """
    work_date = work_date or datetime.now(ZoneInfo("Asia/Manila")).date()
    if region_code not in catalog()["region_codes"]:
        raise PlanningConflict("invalid_region")
    tracking_assignment_ids = list(dict.fromkeys([
        *(auto_assignment_ids or []),
        *([auto_assignment_id] if auto_assignment_id is not None else []),
    ]))

    # The advisory lock covers empty-shift scopes too, where there is no shift
    # row available to serialize duplicate trigger requests.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:scope_key), 19471)"), {
            "scope_key": f"automatic-planning:{work_date.isoformat()}:{region_code}",
        })

    shift_rows = (
        db.query(AgentShift, User)
        .join(User, User.id == AgentShift.agent_id)
        .filter(
            AgentShift.work_date == work_date,
            AgentShift.region_code == region_code,
            AgentShift.is_available.is_(True),
            User.role == "agent",
            User.is_active.is_(True),
        )
        .order_by(AgentShift.agent_id)
        .with_for_update()
        .all()
    )
    shifts_by_agent = {shift.agent_id: shift for shift, _agent in shift_rows}
    agents_by_id = {agent.id: agent for _shift, agent in shift_rows}
    requested_agent_ids = sorted(shifts_by_agent)

    all_open_assigned = db.query(Investigation).filter(
        Investigation.assigned_agent_id.in_(requested_agent_ids),
        Investigation.deleted_at.is_(None),
        Investigation.status.in_(("pending", "assigned")),
    ).order_by(Investigation.id).all() if requested_agent_ids else []
    assigned_by_agent: dict[int, list[Investigation]] = {}
    for case in all_open_assigned:
        assigned_by_agent.setdefault(case.assigned_agent_id, []).append(case)

    # Do not replace a published route for an agent whose existing official
    # stops cannot be represented in a confirmed route in this scope.
    eligible_agent_ids = [
        agent_id
        for agent_id in requested_agent_ids
        if all(
            case.region_code == region_code and case.location_confirmed
            for case in assigned_by_agent.get(agent_id, [])
        )
    ]
    eligible_shifts = [shifts_by_agent[agent_id] for agent_id in eligible_agent_ids]
    locked_cases = [
        case
        for agent_id in eligible_agent_ids
        for case in assigned_by_agent.get(agent_id, [])
    ]
    candidates = db.query(Investigation).filter(
        Investigation.region_code == region_code,
        Investigation.deleted_at.is_(None),
        Investigation.status == "pending",
        Investigation.assigned_agent_id.is_(None),
        Investigation.location_confirmed_at.is_not(None),
        Investigation.latitude.is_not(None),
        Investigation.longitude.is_not(None),
    ).order_by(Investigation.h3_r7, Investigation.h3_r8, Investigation.id).all()
    excluded_ids = exclude_investigation_ids or set()
    candidates = [case for case in candidates if case.id not in excluded_ids]

    # H3 provides a stable geographic batching order; it never chooses a vehicle.
    selected_cases = list(locked_cases)
    selected_ids = {case.id for case in selected_cases}
    coordinates = {
        (round(shift.start_latitude, 6), round(shift.start_longitude, 6))
        for shift in eligible_shifts
    }
    for shift in eligible_shifts:
        if shift.end_latitude is not None:
            coordinates.add((round(shift.end_latitude, 6), round(shift.end_longitude, 6)))
    for case in selected_cases:
        coordinates.add((round(case.latitude, 6), round(case.longitude, 6)))

    overflow = []
    for case in candidates:
        if case.id in selected_ids:
            continue
        point = (round(case.latitude, 6), round(case.longitude, 6))
        if len(selected_cases) >= 80 or len(coordinates | {point}) > min(80, PLANNING_MAX_LOCATIONS):
            overflow.append(case.id)
            continue
        selected_cases.append(case)
        selected_ids.add(case.id)
        coordinates.add(point)

    if not selected_cases:
        db.commit()
        return None

    selected_candidate_ids = selected_ids - {case.id for case in locked_cases}
    if overflow and not selected_candidate_ids:
        failed = PlanningRun(
            requested_by_id=requester.id,
            work_date=work_date,
            region_code=region_code,
            investigation_ids=sorted(overflow[:80]),
            agent_ids=eligible_agent_ids,
            locked_assignments=[],
            auto_publish=True,
            auto_assignment_id=auto_assignment_id,
            auto_assignment_ids=tracking_assignment_ids,
            status="failed",
            error_code="planning_scope_capacity_exceeded",
            finished_at=datetime.now(timezone.utc),
        )
        db.add(failed)
        db.commit()
        db.refresh(failed)
        _link_auto_route_run(db, failed)
        db.commit()
        return failed

    investigation_ids = sorted(selected_ids)
    locked_assignments = [
        LockedAssignment(investigation_id=case.id, agent_id=case.assigned_agent_id)
        for case in locked_cases
        if case.assigned_agent_id in eligible_agent_ids
    ]

    active_runs = (
        db.query(PlanningRun)
        .filter(
            PlanningRun.work_date == work_date,
            PlanningRun.region_code == region_code,
            PlanningRun.auto_publish.is_(True),
            PlanningRun.status.in_(("queued", "running", "ready")),
        )
        .order_by(PlanningRun.id.desc())
        .with_for_update()
        .all()
    )
    if active_runs:
        run = active_runs[0]
        existing_ids = set(run.investigation_ids or [])
        if run.status == "queued":
            # Update a queued run in place so several location confirmations
            # within the debounce window produce one optimizer invocation.
            run.investigation_ids = investigation_ids
            run.agent_ids = eligible_agent_ids
            run.locked_assignments = [
                {"investigation_id": item.investigation_id, "agent_id": item.agent_id}
                for item in locked_assignments
            ]
            cases_for_digest = selected_cases
            run.input_digest = _digest(_snapshot(db, run, cases_for_digest, eligible_shifts, [agents_by_id[key] for key in eligible_agent_ids]))
            run.auto_replan_requested = run.auto_replan_requested or bool(overflow and selected_candidate_ids)
        elif set(investigation_ids) != existing_ids or overflow:
            run.auto_replan_requested = True
        if auto_assignment_id is not None:
            run.auto_assignment_id = auto_assignment_id
        run.auto_assignment_ids = list(dict.fromkeys([
            *(run.auto_assignment_ids or []),
            *tracking_assignment_ids,
        ]))
        db.commit()
        _link_auto_route_run(db, run)
        db.commit()
        return run

    request = PlanningRunCreate(
        work_date=work_date,
        region_code=region_code,
        investigation_ids=investigation_ids,
        agent_ids=eligible_agent_ids,
        locked_assignments=locked_assignments,
    )
    try:
        with db.begin_nested():
            run = create_run(db, request, requester, commit=False)
    except PlanningConflict as error:
        # Preserve a durable failure record so an over-sized or invalid scope
        # appears in operations monitoring instead of silently remaining pending.
        run = PlanningRun(
            requested_by_id=requester.id,
            work_date=work_date,
            region_code=region_code,
            investigation_ids=investigation_ids,
            agent_ids=eligible_agent_ids,
            locked_assignments=[
                {"investigation_id": item.investigation_id, "agent_id": item.agent_id}
                for item in locked_assignments
            ],
            auto_publish=True,
            auto_assignment_id=auto_assignment_id,
            auto_assignment_ids=tracking_assignment_ids,
            status="failed",
            error_code=str(error) or "planning_scope_invalid",
            finished_at=datetime.now(timezone.utc),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        _link_auto_route_run(db, run)
        db.commit()
        return run

    run.auto_publish = True
    run.auto_assignment_id = auto_assignment_id
    run.auto_assignment_ids = tracking_assignment_ids
    run.auto_replan_requested = bool(overflow and selected_candidate_ids)
    db.commit()
    db.refresh(run)
    _link_auto_route_run(db, run)
    db.commit()
    try:
        from app.workers.tasks import optimize_planning_run

        optimize_planning_run.apply_async(args=[run.id], countdown=3)
    except Exception:
        db.refresh(run)
        run.status = "failed"
        run.error_code = "queue_unavailable"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
    return run


def queue_assignment_route_refresh(
    db: Session,
    assignment_id: int,
    affected_agent_ids: list[int],
    requester: User,
) -> InvestigationAssignment | None:
    assignment = (
        db.query(InvestigationAssignment)
        .filter(InvestigationAssignment.id == assignment_id)
        .with_for_update()
        .first()
    )
    if assignment is None:
        return None
    investigation = db.get(Investigation, assignment.investigation_id)
    if investigation is None:
        return assignment

    work_date = datetime.now(ZoneInfo("Asia/Manila")).date()
    impacted_ids = sorted(set(affected_agent_ids) | {assignment.agent_id})
    shifts = db.query(AgentShift).filter(
        AgentShift.agent_id.in_(impacted_ids), AgentShift.work_date == work_date,
    ).all() if impacted_ids else []
    region_codes = {investigation.region_code} if investigation.region_code else set()
    region_codes.update(shift.region_code for shift in shifts)
    assignment.auto_route_work_date = work_date
    assignment.auto_route_agent_ids = impacted_ids
    assignment.auto_route_run_ids = []
    assignment.auto_route_errors = []
    assignment.auto_route_status = "queued"
    db.commit()

    run_ids: list[int] = []
    errors: list[str] = []
    for region_code in sorted(region_codes):
        run = queue_automatic_planning(
            db,
            region_code,
            requester,
            work_date,
            auto_assignment_id=assignment.id,
        )
        if run is not None:
            run_ids.append(run.id)
            if run.status == "failed" and run.error_code:
                errors.append(run.error_code)
    refreshed = db.get(InvestigationAssignment, assignment.id)
    if refreshed is None:
        return None
    refreshed.auto_route_run_ids = list(dict.fromkeys(run_ids))
    runs = db.query(PlanningRun).filter(PlanningRun.id.in_(run_ids)).all() if run_ids else []
    refreshed.auto_route_agent_ids = sorted(
        set(impacted_ids) | {agent_id for run in runs for agent_id in (run.agent_ids or [])}
    )
    refreshed.auto_route_errors = list(dict.fromkeys(errors))
    refreshed.auto_route_status = "queued" if any(run.status in {"queued", "running", "ready"} for run in runs) else "failed"
    db.commit()
    return sync_assignment_route_refresh(db, assignment.id)


def queue_shift_route_refresh(
    db: Session,
    agent_id: int,
    work_date: date,
    requester: User,
) -> PlanningRun | None:
    """Re-plan confirmed work for the date after shift eligibility changes."""
    shift = db.query(AgentShift).filter(
        AgentShift.agent_id == agent_id,
        AgentShift.work_date == work_date,
    ).first()
    if shift is None:
        return None
    return queue_automatic_planning(db, shift.region_code, requester, work_date)


def sync_assignment_route_refresh(
    db: Session,
    assignment_id: int,
) -> InvestigationAssignment | None:
    assignment = db.get(InvestigationAssignment, assignment_id)
    if assignment is None or assignment.auto_route_status is None:
        return assignment
    run_ids = assignment.auto_route_run_ids or []
    runs = db.query(PlanningRun).filter(PlanningRun.id.in_(run_ids)).all() if run_ids else []
    by_id = {run.id: run for run in runs}
    active_statuses = {"queued", "running", "ready"}
    has_active = any(run.status in active_statuses for run in runs)
    if has_active:
        assignment.auto_route_status = (
            "running" if any(run.status in {"running", "ready"} for run in runs) else "queued"
        )
    else:
        errors = list(assignment.auto_route_errors or [])
        for run_id in run_ids:
            run = by_id.get(run_id)
            if run is None:
                errors.append("planning_run_missing")
            elif run.status in {"failed", "stale"} and run.error_code:
                errors.append(run.error_code)
        assignment.auto_route_errors = list(dict.fromkeys(errors))
        if errors or any(run.status != "applied" for run in runs):
            assignment.auto_route_status = (
                "partially_published"
                if any(run.status == "applied" for run in runs)
                else "failed"
            )
        elif runs:
            assignment.auto_route_status = "published"
        else:
            assignment.auto_route_status = "failed"
            assignment.auto_route_errors = ["no_routeable_assigned_work"]
    db.commit()
    db.refresh(assignment)
    return assignment


def _snapshot(db: Session, run: PlanningRun, cases: list[Investigation], shifts: list[AgentShift], agents: list[User]) -> dict:
    active_assignments = (
        db.query(InvestigationAssignment)
        .filter(
            InvestigationAssignment.investigation_id.in_(run.investigation_ids),
            InvestigationAssignment.is_active.is_(True),
        )
        .all()
    ) if run.investigation_ids else []
    return {
        "date": run.work_date.isoformat(),
        "region": run.region_code,
        "cases": [
            {
                "id": case.id,
                "status": case.status,
                "deleted": _iso_utc(case.deleted_at),
                "region": case.region_code,
                "lat": case.latitude,
                "lon": case.longitude,
                "location_source": case.location_source,
                "location_confirmed_at": _iso_utc(case.location_confirmed_at),
                "priority": case.priority,
                "service": case.service_duration_seconds,
                "not_before": _iso_utc(case.visit_not_before_at),
                "due": _iso_utc(case.visit_due_at),
                "h3": [case.h3_r7, case.h3_r8, case.h3_r9],
            }
            for case in sorted(cases, key=lambda item: item.id)
        ],
        "assignments": [
            {"id": item.id, "investigation": item.investigation_id, "agent": item.agent_id, "source": item.assignment_source, "note": item.note}
            for item in sorted(active_assignments, key=lambda item: item.investigation_id)
        ],
        "shifts": [
            {
                "id": shift.id,
                "agent": shift.agent_id,
                "available": shift.is_available,
                "region": shift.region_code,
                "start": _as_utc(shift.shift_starts_at).isoformat(),
                "end": _as_utc(shift.shift_ends_at).isoformat(),
                "start_point": [shift.start_latitude, shift.start_longitude],
                "end_point": [shift.end_latitude, shift.end_longitude],
                "max_visits": shift.max_visits,
                "max_open_cases": shift.max_open_cases,
                "current_run": shift.current_planning_run_id,
            }
            for shift in sorted(shifts, key=lambda item: item.agent_id)
        ],
        "agents": [{"id": user.id, "role": user.role, "active": user.is_active} for user in sorted(agents, key=lambda item: item.id)],
        "locked": run.locked_assignments,
    }


def _connected_components(durations: list[list[float | None]], distances: list[list[float | None]]) -> list[list[int]]:
    # VROOM requires a complete matrix for every submitted problem. OSRM can
    # return asymmetric nulls (one-way roads, disconnected islands), so build
    # deterministic complete-link groups instead of ordinary graph components.
    # The greedy partition can yield more groups than a minimum clique cover,
    # which is safe and bounded by the 80-point planning cap.
    components: list[list[int]] = []
    for candidate in range(len(durations)):
        for component in components:
            if all(
                durations[candidate][member] is not None
                and durations[member][candidate] is not None
                and distances[candidate][member] is not None
                and distances[member][candidate] is not None
                for member in component
            ):
                component.append(candidate)
                break
        else:
            components.append([candidate])
    return components


def _valid_cost_matrix(matrix, size: int) -> bool:
    if not isinstance(matrix, list) or len(matrix) != size:
        return False
    for row in matrix:
        if not isinstance(row, list) or len(row) != size:
            return False
        for value in row:
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
                return False
    return True


def _run_component(
    component: list[int],
    point_indexes: dict[tuple[float, float], int],
    coordinates: list[tuple[float, float]],
    durations: list[list[float | None]],
    distances: list[list[float | None]],
    cases: list[Investigation],
    shifts: list[AgentShift],
    locked: dict[int, int],
    open_case_counts: dict[int, int],
    solver: VROOMClient,
) -> list[dict]:
    local_index = {global_index: index for index, global_index in enumerate(component)}
    component_set = set(component)
    component_durations = [[int(durations[source][target]) for target in component] for source in component]
    component_distances = [[int(distances[source][target]) for target in component] for source in component]
    jobs = []
    case_by_id = {case.id: case for case in cases}
    for case in cases:
        coordinate = (round(case.latitude, 6), round(case.longitude, 6))
        index = point_indexes[coordinate]
        if index not in component_set:
            continue
        job = {
            "id": case.id,
            "location": [case.longitude, case.latitude],
            "location_index": local_index[index],
            "service": case.service_duration_seconds,
            "priority": PRIORITY_VALUES.get(case.priority, 10),
        }
        windows = []
        if case.visit_not_before_at or case.visit_due_at:
            latest_start = _as_utc(case.visit_due_at).timestamp() - case.service_duration_seconds if case.visit_due_at else None
            windows.append([
                _epoch(case.visit_not_before_at) if case.visit_not_before_at else min(_epoch(s.shift_starts_at) for s in shifts),
                int(latest_start) if latest_start is not None else max(_epoch(s.shift_ends_at) for s in shifts),
            ])
            job["time_windows"] = windows
        locked_agent = locked.get(case.id)
        if locked_agent:
            job["skills"] = [1_000_000 + locked_agent]
        jobs.append(job)

    vehicles = []
    shift_by_agent = {shift.agent_id: shift for shift in shifts}
    for shift in shifts:
        start = (round(shift.start_latitude, 6), round(shift.start_longitude, 6))
        end = (round(shift.end_latitude, 6), round(shift.end_longitude, 6)) if shift.end_latitude is not None else start
        start_global = point_indexes[start]
        end_global = point_indexes[end]
        if start_global not in component_set or end_global not in component_set:
            continue
        remaining_open = max(0, shift.max_open_cases - open_case_counts.get(shift.agent_id, 0))
        assigned_selected_count = sum(
            1 for case in cases if case.assigned_agent_id == shift.agent_id
        )
        task_cap = min(shift.max_visits, remaining_open + assigned_selected_count)
        if task_cap < 1:
            continue
        vehicles.append({
            "id": shift.agent_id,
            "profile": "car",
            "start": [start[1], start[0]],
            "end": [end[1], end[0]],
            "start_index": local_index[start_global],
            "end_index": local_index[end_global],
            "time_window": [_epoch(shift.shift_starts_at), _epoch(shift.shift_ends_at)],
            "max_tasks": max(1, task_cap),
            "skills": [1_000_000 + shift.agent_id],
        })

    if not jobs or not vehicles:
        return []
    payload = {
        "vehicles": vehicles,
        "jobs": jobs,
        "matrices": {"car": {"durations": component_durations, "distances": component_distances}},
    }
    solution = solver.solve(payload)
    expected_job_ids = {job["id"] for job in jobs}
    valid_vehicle_ids = {vehicle["id"] for vehicle in vehicles}
    if not isinstance(solution.get("routes"), list) or not isinstance(solution.get("unassigned"), list):
        raise RoutingUnavailable("vroom_solution_shape_invalid")
    outcomes: list[dict] = []
    reported_ids: set[int] = set()
    reported_vehicles: set[int] = set()
    for route in solution.get("routes", []):
        if not isinstance(route, dict) or isinstance(route.get("vehicle"), bool) or not isinstance(route.get("vehicle"), int):
            raise RoutingUnavailable("vroom_solution_shape_invalid")
        agent_id = route["vehicle"]
        if agent_id not in valid_vehicle_ids or agent_id in reported_vehicles:
            raise RoutingUnavailable("vroom_solution_vehicle_invalid")
        reported_vehicles.add(agent_id)
        steps = route.get("steps")
        if (
            not isinstance(steps, list)
            or len(steps) < 2
            or not isinstance(steps[0], dict)
            or steps[0].get("type") != "start"
            or not isinstance(steps[-1], dict)
            or steps[-1].get("type") != "end"
        ):
            raise RoutingUnavailable("vroom_solution_shape_invalid")
        shift = shift_by_agent[agent_id]
        previous_index = point_indexes[(round(shift.start_latitude, 6), round(shift.start_longitude, 6))]
        start_arrival = steps[0].get("arrival")
        if isinstance(start_arrival, bool) or not isinstance(start_arrival, (int, float)) or not isfinite(start_arrival):
            raise RoutingUnavailable("vroom_solution_arrival_invalid")
        previous_arrival = int(start_arrival)
        if previous_arrival < _epoch(shift.shift_starts_at) or previous_arrival > _epoch(shift.shift_ends_at):
            raise RoutingUnavailable("vroom_solution_schedule_invalid")
        previous_service = 0
        sequence = 0
        for step in steps[1:-1]:
            if not isinstance(step, dict) or not isinstance(step.get("type"), str):
                raise RoutingUnavailable("vroom_solution_shape_invalid")
            if step.get("type") != "job":
                continue
            if isinstance(step.get("id"), bool) or not isinstance(step.get("id"), int):
                raise RoutingUnavailable("vroom_solution_shape_invalid")
            case = case_by_id.get(step["id"])
            if case is None or case.id not in expected_job_ids or case.id in reported_ids:
                raise RoutingUnavailable("vroom_solution_job_invalid")
            arrival = step.get("arrival")
            if isinstance(arrival, bool) or not isinstance(arrival, (int, float)) or not isfinite(arrival):
                raise RoutingUnavailable("vroom_solution_arrival_invalid")
            arrival = int(arrival)
            coordinate = (round(case.latitude, 6), round(case.longitude, 6))
            current_index = point_indexes[coordinate]
            travel_seconds = int(durations[previous_index][current_index])
            earliest = previous_arrival + previous_service + travel_seconds
            if case.visit_not_before_at:
                earliest = max(earliest, _epoch(case.visit_not_before_at))
            if arrival < earliest or arrival + case.service_duration_seconds > _epoch(shift.shift_ends_at):
                raise RoutingUnavailable("vroom_solution_schedule_invalid")
            if case.visit_due_at and arrival + case.service_duration_seconds > _epoch(case.visit_due_at):
                raise RoutingUnavailable("vroom_solution_schedule_invalid")
            if case.id in locked and locked[case.id] != agent_id:
                raise RoutingUnavailable("vroom_solution_locked_assignment_invalid")
            sequence += 1
            outcomes.append({
                "investigation_id": case.id,
                "agent_id": agent_id,
                "outcome": "assigned",
                "reason": None,
                "sequence": sequence,
                "estimated_arrival_at": datetime.fromtimestamp(arrival, timezone.utc),
                "travel_seconds": travel_seconds,
                "travel_metres": int(distances[previous_index][current_index]),
            })
            reported_ids.add(case.id)
            previous_index = current_index
            previous_arrival = arrival
            previous_service = case.service_duration_seconds
        end_arrival = steps[-1].get("arrival")
        if isinstance(end_arrival, bool) or not isinstance(end_arrival, (int, float)) or not isfinite(end_arrival):
            raise RoutingUnavailable("vroom_solution_arrival_invalid")
        end_coordinate = (
            (round(shift.end_latitude, 6), round(shift.end_longitude, 6))
            if shift.end_latitude is not None
            else (round(shift.start_latitude, 6), round(shift.start_longitude, 6))
        )
        end_index = point_indexes[end_coordinate]
        return_earliest = previous_arrival + previous_service + int(durations[previous_index][end_index])
        if int(end_arrival) < return_earliest or int(end_arrival) > _epoch(shift.shift_ends_at):
            raise RoutingUnavailable("vroom_solution_schedule_invalid")
    for unassigned in solution.get("unassigned", []):
        if not isinstance(unassigned, dict) or isinstance(unassigned.get("id"), bool) or not isinstance(unassigned.get("id"), int):
            raise RoutingUnavailable("vroom_solution_shape_invalid")
        investigation_id = unassigned["id"]
        if investigation_id not in expected_job_ids or investigation_id in reported_ids:
            raise RoutingUnavailable("vroom_solution_job_invalid")
        outcomes.append({"investigation_id": investigation_id, "agent_id": None, "outcome": "unassigned", "reason": "no_feasible_route_under_constraints"})
        reported_ids.add(investigation_id)
    if reported_ids != expected_job_ids:
        raise RoutingUnavailable("vroom_solution_incomplete")
    return outcomes


def _record_ready_run(
    db: Session,
    run: PlanningRun,
    expected_input_digest: str | None,
    case_rows: list[Investigation],
    shifts: list[AgentShift],
    agents: list[User],
    assignment_by_case: dict[int, InvestigationAssignment],
    preflight: dict[int, tuple[str, str | None]],
    outcome_by_case: dict[int, dict],
    route_geometries: list[dict] | None = None,
) -> bool:
    # Routing calls run outside the database transaction. Re-read all inputs
    # under the run lock before publishing so mid-optimization changes cannot
    # turn an obsolete result into a ready plan.
    db.flush()
    db.expire_all()
    run = (
        db.query(PlanningRun)
        .filter(PlanningRun.id == run.id)
        .with_for_update()
        .populate_existing()
        .first()
    )
    if run is None or run.status != "running":
        db.rollback()
        return False
    case_rows = db.query(Investigation).filter(
        Investigation.id.in_(run.investigation_ids)
    ).order_by(Investigation.id).all() if run.investigation_ids else []
    shifts = db.query(AgentShift).filter(
        AgentShift.agent_id.in_(run.agent_ids), AgentShift.work_date == run.work_date
    ).order_by(AgentShift.agent_id).all() if run.agent_ids else []
    agents = db.query(User).filter(User.id.in_(run.agent_ids)).order_by(User.id).all() if run.agent_ids else []
    current_input_digest = _digest(_snapshot(db, run, case_rows, shifts, agents))
    if expected_input_digest and current_input_digest != expected_input_digest:
        run.status = "stale"
        run.error_code = "inputs_changed"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        _log_planning_event(
            "planning.run_stale",
            planning_run_id=run.id,
            reason=run.error_code,
            stage="before_publish",
        )
        return False

    db.query(PlanningRoute).filter(PlanningRoute.planning_run_id == run.id).delete()
    for geometry in route_geometries or []:
        db.add(PlanningRoute(planning_run_id=run.id, **geometry))
    db.query(PlanningItem).filter(PlanningItem.planning_run_id == run.id).delete()
    for case_id in run.investigation_ids:
        outcome, reason = preflight.get(case_id, ("unassigned", "no_feasible_route_under_constraints"))
        proposal = outcome_by_case.get(case_id, {})
        db.add(PlanningItem(
            planning_run_id=run.id,
            investigation_id=case_id,
            agent_id=proposal.get("agent_id"),
            outcome=outcome,
            reason=reason,
            sequence=proposal.get("sequence"),
            estimated_arrival_at=proposal.get("estimated_arrival_at"),
            travel_seconds=proposal.get("travel_seconds"),
            travel_metres=proposal.get("travel_metres"),
            prior_assignment_id=assignment_by_case[case_id].id if case_id in assignment_by_case else None,
        ))

    run.input_digest = _digest(_snapshot(db, run, case_rows, shifts, agents))
    run.osrm_dataset = OSRM_DATASET_VERSION
    run.status = "ready"
    run.finished_at = datetime.now(timezone.utc)
    run.error_code = None
    db.flush()
    items = db.query(PlanningItem).filter(PlanningItem.planning_run_id == run.id).order_by(PlanningItem.investigation_id).all()
    run.result_digest = _digest({
        "run": run.id,
        "input": run.input_digest,
        "routes": [[route["agent_id"], route["geometry_digest"]] for route in route_geometries or []],
        "items": [
            [item.investigation_id, item.agent_id, item.outcome, item.reason, item.sequence,
             item.estimated_arrival_at.isoformat() if item.estimated_arrival_at else None,
             item.travel_seconds, item.travel_metres]
            for item in items
        ],
    })
    db.commit()
    unassigned_reasons = Counter(
        reason
        for outcome, reason in preflight.values()
        if outcome == "unassigned" and reason
    )
    _log_planning_event(
        "planning.run_ready",
        planning_run_id=run.id,
        work_date=run.work_date.isoformat(),
        region_code=run.region_code,
        duration_seconds=round((_as_utc(run.finished_at) - _as_utc(run.started_at)).total_seconds(), 3)
        if run.started_at and run.finished_at else None,
        assigned_count=sum(1 for outcome, _ in preflight.values() if outcome == "assigned"),
        unassigned_count=sum(1 for outcome, _ in preflight.values() if outcome == "unassigned"),
        unassigned_reasons=dict(sorted(unassigned_reasons.items())),
        road_snap_warning_count=len(run.warnings or []),
        osrm_dataset=run.osrm_dataset,
    )
    return True


def execute_run(db: Session, run_id: int) -> None:
    run = db.query(PlanningRun).filter(PlanningRun.id == run_id).with_for_update().first()
    if run is None or run.status != "queued":
        return
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    run.error_code = None
    run.warnings = []
    db.commit()
    expected_input_digest = run.input_digest
    _log_planning_event(
        "planning.run_started",
        planning_run_id=run.id,
        queue_age_seconds=round((_as_utc(run.started_at) - _as_utc(run.created_at)).total_seconds(), 3)
        if run.created_at else None,
        investigation_count=len(run.investigation_ids),
        agent_count=len(run.agent_ids),
        osrm_dataset=OSRM_DATASET_VERSION,
    )

    osrm = None
    solver = None
    try:
        osrm = OSRMClient()
        solver = VROOMClient()
        case_rows = (
            db.query(Investigation)
            .filter(Investigation.id.in_(run.investigation_ids))
            .order_by(Investigation.id)
            .all()
        ) if run.investigation_ids else []
        shifts = (
            db.query(AgentShift)
            .filter(AgentShift.agent_id.in_(run.agent_ids), AgentShift.work_date == run.work_date)
            .order_by(AgentShift.agent_id)
            .all()
        ) if run.agent_ids else []
        agents = db.query(User).filter(User.id.in_(run.agent_ids)).order_by(User.id).all() if run.agent_ids else []
        current_input_digest = _digest(_snapshot(db, run, case_rows, shifts, agents))
        if run.input_digest and current_input_digest != run.input_digest:
            run.status = "stale"
            run.error_code = "inputs_changed"
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            _log_planning_event(
                "planning.run_stale",
                planning_run_id=run.id,
                reason=run.error_code,
                stage="before_routing",
            )
            return
        case_by_id = {case.id: case for case in case_rows}
        shift_by_agent = {shift.agent_id: shift for shift in shifts}
        agent_by_id = {agent.id: agent for agent in agents}
        locked = {item["investigation_id"]: item["agent_id"] for item in run.locked_assignments}
        active_assignments = (
            db.query(InvestigationAssignment)
            .filter(InvestigationAssignment.investigation_id.in_(run.investigation_ids), InvestigationAssignment.is_active.is_(True))
            .all()
        ) if run.investigation_ids else []
        assignment_by_case = {item.investigation_id: item for item in active_assignments}

        preflight: dict[int, tuple[str, str | None]] = {}
        eligible_agents: list[AgentShift] = []
        for agent_id in run.agent_ids:
            agent = agent_by_id.get(agent_id)
            shift = shift_by_agent.get(agent_id)
            if agent and agent.role == "agent" and agent.is_active and shift and shift.is_available and shift.region_code == run.region_code:
                if shift.start_latitude is not None and shift.start_longitude is not None:
                    eligible_agents.append(shift)

        if not eligible_agents:
            for case in case_rows:
                if case.deleted_at is None and case.status in {"pending", "assigned"} and case.location_confirmed:
                    preflight[case.id] = ("unassigned", "no_available_agents")
            _record_ready_run(
                db, run, expected_input_digest, case_rows, shifts, agents,
                assignment_by_case, preflight, {},
            )
            return

        cases: list[Investigation] = []
        for case_id in run.investigation_ids:
            case = case_by_id.get(case_id)
            if case is None or case.deleted_at is not None:
                preflight[case_id] = ("unassigned", "investigation_unavailable")
                continue
            if case.region_code != run.region_code:
                preflight[case_id] = ("unassigned", "region_mismatch")
                continue
            if case.status not in {"pending", "assigned"}:
                preflight[case_id] = ("unassigned", "status_not_assignable")
                continue
            if not case.location_confirmed:
                preflight[case_id] = ("unassigned", "location_unconfirmed")
                continue
            current = assignment_by_case.get(case.id)
            fixed_agent = locked.get(case.id) or case.assigned_agent_id
            if current and fixed_agent != current.agent_id:
                raise PlanningConflict("assignment_lock_conflict")
            if fixed_agent and fixed_agent not in {shift.agent_id for shift in eligible_agents}:
                preflight[case_id] = ("unassigned", "locked_agent_unavailable")
                continue
            if fixed_agent:
                locked[case.id] = fixed_agent
            cases.append(case)

        if not cases:
            raise PlanningConflict("no_eligible_investigations")

        open_counts = {
            agent_id: int(db.query(func.count(Investigation.id)).filter(
                Investigation.assigned_agent_id == agent_id,
                Investigation.deleted_at.is_(None),
                Investigation.status.in_(OPEN_STATUSES),
            ).scalar() or 0)
            for agent_id in run.agent_ids
        }

        used_shifts = [shift for shift in eligible_agents if open_counts.get(shift.agent_id, 0) < shift.max_open_cases or any(case.assigned_agent_id == shift.agent_id for case in cases)]
        if not used_shifts:
            for case in cases:
                preflight[case.id] = ("unassigned", "agent_open_case_limit")
            _record_ready_run(
                db, run, expected_input_digest, case_rows, shifts, agents,
                assignment_by_case, preflight, {},
            )
            return

        earliest_shift_start = min(_epoch(shift.shift_starts_at) for shift in used_shifts)
        latest_shift_end = max(_epoch(shift.shift_ends_at) for shift in used_shifts)
        impossible_windows = set()
        for case in cases:
            earliest_start = _epoch(case.visit_not_before_at) if case.visit_not_before_at else earliest_shift_start
            latest_start = _epoch(case.visit_due_at) - case.service_duration_seconds if case.visit_due_at else latest_shift_end
            if earliest_start > latest_start:
                preflight[case.id] = ("unassigned", "deadline_before_service_window")
                impossible_windows.add(case.id)
        cases = [case for case in cases if case.id not in impossible_windows]
        if not cases:
            _record_ready_run(
                db, run, expected_input_digest, case_rows, shifts, agents,
                assignment_by_case, preflight, {},
            )
            return

        coordinate_for_case = {(round(case.latitude, 6), round(case.longitude, 6)) for case in cases}
        for shift in used_shifts:
            coordinate_for_case.add((round(shift.start_latitude, 6), round(shift.start_longitude, 6)))
            if shift.end_latitude is not None:
                coordinate_for_case.add((round(shift.end_latitude, 6), round(shift.end_longitude, 6)))
        coordinates = sorted(coordinate_for_case)
        if len(coordinates) > min(80, PLANNING_MAX_LOCATIONS):
            raise PlanningConflict("run_too_large")

        snap_coordinates = sorted(coordinate_for_case)
        snap_waypoints = osrm.nearest_many(snap_coordinates)
        if len(snap_waypoints) != len(snap_coordinates):
            raise RoutingUnavailable("osrm_snap_shape_invalid")
        snap_distances = {}
        for coordinate, waypoint in zip(snap_coordinates, snap_waypoints):
            if not isinstance(waypoint, dict):
                raise RoutingUnavailable("osrm_snap_shape_invalid")
            if waypoint.get("unroutable") is True:
                snap_distances[coordinate] = float("inf")
                continue
            distance = waypoint.get("distance")
            if isinstance(distance, bool) or not isinstance(distance, (int, float)) or not isfinite(distance) or distance < 0:
                raise RoutingUnavailable("osrm_snap_shape_invalid")
            snap_distances[coordinate] = float(distance)
        run.warnings = [
            {"type": "road_snap_distance", "latitude": coordinate[0], "longitude": coordinate[1], "distance_metres": distance}
            for coordinate, distance in snap_distances.items()
            if 500 < distance <= 2000
        ]
        valid_shifts: list[AgentShift] = []
        for shift in used_shifts:
            start = (round(shift.start_latitude, 6), round(shift.start_longitude, 6))
            end = (round(shift.end_latitude, 6), round(shift.end_longitude, 6)) if shift.end_latitude is not None else start
            if snap_distances.get(start, 0) <= 2000 and snap_distances.get(end, 0) <= 2000:
                valid_shifts.append(shift)
        if not valid_shifts:
            for case in cases:
                preflight[case.id] = ("unassigned", "no_routable_agent_start")
            _record_ready_run(
                db, run, expected_input_digest, case_rows, shifts, agents,
                assignment_by_case, preflight, {},
            )
            return
        used_shifts = valid_shifts

        for case in cases:
            coordinate = (round(case.latitude, 6), round(case.longitude, 6))
            if snap_distances[coordinate] > 2000:
                preflight[case.id] = ("unassigned", "road_snap_too_far")
        cases = [case for case in cases if preflight.get(case.id, (None, None))[1] != "road_snap_too_far"]
        if not cases:
            _record_ready_run(db, run, expected_input_digest, case_rows, shifts, agents, assignment_by_case, preflight, {})
            return

        # Drop depot points for agents that failed the snap test before requesting a matrix.
        coordinate_for_case = {(round(case.latitude, 6), round(case.longitude, 6)) for case in cases}
        for shift in used_shifts:
            coordinate_for_case.add((round(shift.start_latitude, 6), round(shift.start_longitude, 6)))
            if shift.end_latitude is not None:
                coordinate_for_case.add((round(shift.end_latitude, 6), round(shift.end_longitude, 6)))
        coordinates = sorted(coordinate_for_case)
        if len(coordinates) > min(80, PLANNING_MAX_LOCATIONS):
            raise PlanningConflict("run_too_large")
        point_indexes = {coordinate: index for index, coordinate in enumerate(coordinates)}
        table = osrm.table(coordinates)
        durations = table.get("durations") or []
        distances = table.get("distances") or []
        if not _valid_cost_matrix(durations, len(coordinates)) or not _valid_cost_matrix(distances, len(coordinates)):
            raise RoutingUnavailable("osrm_matrix_shape_invalid")

        components = _connected_components(durations, distances)
        outcomes: list[dict] = []
        covered_case_ids: set[int] = set()
        for component in components:
            component_case_ids = {
                case.id for case in cases
                if point_indexes[(round(case.latitude, 6), round(case.longitude, 6))] in component
            }
            component_shift_ids = {
                shift.agent_id for shift in used_shifts
                if point_indexes[(round(shift.start_latitude, 6), round(shift.start_longitude, 6))] in component
            }
            if not component_case_ids:
                continue
            component_cases = [case for case in cases if case.id in component_case_ids]
            component_shifts = [shift for shift in used_shifts if shift.agent_id in component_shift_ids]
            if not component_shifts:
                for case in component_cases:
                    preflight[case.id] = ("unassigned", "no_road_connected_agent")
                continue
            result = _run_component(
                component, point_indexes, coordinates, durations, distances,
                component_cases, component_shifts, locked, open_counts, solver,
            )
            outcomes.extend(result)
            covered_case_ids.update(component_case_ids)
        for case in cases:
            if case.id not in covered_case_ids:
                preflight[case.id] = ("unassigned", "no_road_connected_agent")
        outcome_by_case = {item["investigation_id"]: item for item in outcomes}
        if len(outcome_by_case) != len(outcomes):
            raise RoutingUnavailable("vroom_duplicate_job_result")
        for case_id, agent_id in locked.items():
            result = outcome_by_case.get(case_id)
            if result is None or result.get("agent_id") != agent_id:
                raise PlanningConflict("locked_case_not_feasible")
        for case_id in run.investigation_ids:
            item = outcome_by_case.get(case_id)
            if item:
                preflight[case_id] = (item["outcome"], item.get("reason"))
                if item.get("agent_id") is not None:
                    preflight[case_id] = ("assigned", None)

        route_geometries = _build_route_geometries(osrm, case_rows, shifts, outcome_by_case)
        _record_ready_run(db, run, expected_input_digest, case_rows, shifts, agents, assignment_by_case, preflight, outcome_by_case, route_geometries)
    except Exception as error:
        db.rollback()
        failed = db.query(PlanningRun).filter(PlanningRun.id == run_id).first()
        if failed and failed.status == "running":
            failed.status = "failed"
            failed.error_code = (
                error.args[0]
                if isinstance(error, (PlanningConflict, RoutingUnavailable)) and error.args
                else "optimization_failed"
            )
            failed.finished_at = datetime.now(timezone.utc)
            db.query(PlanningItem).filter(PlanningItem.planning_run_id == run_id).delete()
            db.commit()
            _log_planning_event(
                "planning.run_failed",
                planning_run_id=run_id,
                error_code=failed.error_code,
                duration_seconds=round((_as_utc(failed.finished_at) - _as_utc(failed.started_at)).total_seconds(), 3)
                if failed.started_at and failed.finished_at else None,
                osrm_dataset=OSRM_DATASET_VERSION,
            )
    finally:
        if osrm is not None:
            osrm.close()
        if solver is not None:
            solver.close()


def get_run(db: Session, run_id: int) -> PlanningRun | None:
    return db.query(PlanningRun).filter(PlanningRun.id == run_id).first()


def run_response(db: Session, run: PlanningRun) -> dict:
    items = (
        db.query(PlanningItem, Investigation, User)
        .join(Investigation, Investigation.id == PlanningItem.investigation_id)
        .outerjoin(User, User.id == PlanningItem.agent_id)
        .filter(PlanningItem.planning_run_id == run.id)
        .order_by(PlanningItem.agent_id, PlanningItem.sequence, PlanningItem.investigation_id)
        .all()
    )
    assigned_agents = {item.agent_id for item, _, _ in items if item.outcome == "assigned" and item.agent_id is not None}
    geometry_complete = _geometry_complete(db, run.id, assigned_agents)
    routes = db.query(PlanningRoute, User).join(User, User.id == PlanningRoute.agent_id).filter(PlanningRoute.planning_run_id == run.id).order_by(PlanningRoute.agent_id).all()
    shift_by_agent = {shift.agent_id: shift for shift in db.query(AgentShift).filter(AgentShift.work_date == run.work_date, AgentShift.agent_id.in_(run.agent_ids)).all()}
    return {
        "routes": [route_response(route, agent, shift_by_agent.get(agent.id)) for route, agent in routes],
        "geometry_complete": geometry_complete,
        "investigation_ids": run.investigation_ids,
        "agent_ids": run.agent_ids,
        "id": run.id,
        "auto_publish": run.auto_publish,
        "work_date": run.work_date,
        "region_code": run.region_code,
        "status": run.status,
        "result_digest": run.result_digest,
        "error_code": run.error_code,
        "osrm_dataset": run.osrm_dataset,
        "warnings": run.warnings,
        "created_at": run.created_at,
        "finished_at": run.finished_at,
        "applied_at": run.applied_at,
        "items": [
            {
                "investigation_id": item.investigation_id,
                "reference_number": case.reference_number,
                "address_display": case.address_display,
                "latitude": case.latitude,
                "longitude": case.longitude,
                "priority": case.priority,
                "status": case.status,
                "prior_agent_id": case.assigned_agent_id,
                "service_duration_seconds": case.service_duration_seconds,
                "agent_id": item.agent_id,
                "agent_name": agent.name if agent else None,
                "outcome": item.outcome,
                "reason": item.reason,
                "sequence": item.sequence,
                "estimated_arrival_at": item.estimated_arrival_at,
                "travel_seconds": item.travel_seconds,
                "travel_metres": item.travel_metres,
            }
            for item, case, agent in items
        ],
    }


def apply_run(
    db: Session,
    run_id: int,
    result_digest: str,
    actor: User,
) -> PlanningRun:
    run = db.query(PlanningRun).filter(PlanningRun.id == run_id).first()
    if run is None:
        raise PlanningConflict("planning_run_not_found")
    if run.status == "applied" and run.result_digest == result_digest:
        return run
    if not run.auto_publish:
        raise PlanningConflict("automatic_publication_required")
    if run.status != "ready" or run.result_digest != result_digest:
        raise PlanningConflict("planning_run_not_ready")

    case_ids = sorted(run.investigation_ids)
    cases = db.query(Investigation).filter(Investigation.id.in_(case_ids)).order_by(Investigation.id).with_for_update().all()
    shifts = db.query(AgentShift).filter(AgentShift.agent_id.in_(run.agent_ids), AgentShift.work_date == run.work_date).order_by(AgentShift.agent_id).with_for_update().all()
    agents = db.query(User).filter(User.id.in_(run.agent_ids)).order_by(User.id).with_for_update().all()
    # Lock the plan after its cases, shifts, and agents. Mutation paths use the
    # same entity-first order, avoiding cycles while stale plans are invalidated.
    run = (
        db.query(PlanningRun)
        .filter(PlanningRun.id == run_id)
        .with_for_update()
        .populate_existing()
        .first()
    )
    if run is None:
        raise PlanningConflict("planning_run_not_found")
    if run.status == "applied" and run.result_digest == result_digest:
        return run
    if not run.auto_publish:
        raise PlanningConflict("automatic_publication_required")
    if run.status != "ready" or run.result_digest != result_digest:
        raise PlanningConflict("planning_run_not_ready")
    if len(cases) != len(case_ids):
        run.status = "stale"
        run.error_code = "investigation_changed"
        db.commit()
        raise PlanningConflict("stale_plan")
    if _digest(_snapshot(db, run, cases, shifts, agents)) != run.input_digest:
        run.status = "stale"
        run.error_code = "inputs_changed"
        db.commit()
        raise PlanningConflict("stale_plan")

    case_by_id = {case.id: case for case in cases}
    agent_by_id = {agent.id: agent for agent in agents}
    shift_by_agent = {shift.agent_id: shift for shift in shifts}
    items = db.query(PlanningItem).filter(PlanningItem.planning_run_id == run.id).order_by(PlanningItem.investigation_id).with_for_update().all()
    if len(items) != len(case_ids) or {item.investigation_id for item in items} != set(case_ids):
        raise PlanningConflict("planning_result_incomplete")
    assigned_agents = {item.agent_id for item in items if item.outcome == "assigned" and item.agent_id is not None}
    if assigned_agents and not _geometry_complete(db, run.id, assigned_agents):
        raise PlanningConflict("route_geometry_incomplete")

    locked = {item["investigation_id"]: item["agent_id"] for item in run.locked_assignments}
    sequence_keys: set[tuple[int, int]] = set()

    # Apply is all-or-nothing. Every proposed stop is rechecked under the locks above.
    for item in items:
        if item.outcome == "unassigned":
            if item.agent_id is not None or item.sequence is not None or item.investigation_id in locked:
                raise PlanningConflict("planning_result_invalid")
            continue
        if item.outcome != "assigned" or item.agent_id is None or item.sequence is None or item.sequence < 1:
            raise PlanningConflict("planning_result_invalid")
        if item.travel_seconds is None or item.travel_seconds < 0 or item.travel_metres is None or item.travel_metres < 0:
            raise PlanningConflict("planning_result_invalid")
        if item.estimated_arrival_at is None:
            raise PlanningConflict("planning_result_invalid")
        if (item.agent_id, item.sequence) in sequence_keys:
            raise PlanningConflict("planning_result_invalid")
        sequence_keys.add((item.agent_id, item.sequence))
        if item.investigation_id in locked and locked[item.investigation_id] != item.agent_id:
            raise PlanningConflict("locked_assignment_changed")
        if item.investigation_id not in case_by_id:
            raise PlanningConflict("planning_result_invalid")
        case = case_by_id[item.investigation_id]
        agent = agent_by_id.get(item.agent_id)
        shift = shift_by_agent.get(item.agent_id)
        if not agent or agent.role != "agent" or not agent.is_active or not shift or not shift.is_available:
            raise PlanningConflict("agent_no_longer_eligible")
        arrival = _as_utc(item.estimated_arrival_at)
        end = _as_utc(shift.shift_ends_at)
        if arrival < _as_utc(shift.shift_starts_at) or arrival.timestamp() + case.service_duration_seconds > end.timestamp():
            raise PlanningConflict("agent_schedule_changed")
        if case.visit_not_before_at and arrival < _as_utc(case.visit_not_before_at):
            raise PlanningConflict("visit_window_changed")
        if case.visit_due_at and arrival.timestamp() + case.service_duration_seconds > _as_utc(case.visit_due_at).timestamp():
            raise PlanningConflict("visit_window_changed")

    for item in items:
        if item.outcome != "assigned" or item.agent_id is None:
            continue
        case = case_by_id[item.investigation_id]
        agent = agent_by_id.get(item.agent_id)
        shift = shift_by_agent.get(item.agent_id)
        if case.deleted_at is not None or case.status not in {"pending", "assigned"}:
            raise PlanningConflict("case_no_longer_assignable")
        if not agent or agent.role != "agent" or not agent.is_active or not shift or not shift.is_available:
            raise PlanningConflict("agent_no_longer_eligible")
        if shift.region_code != run.region_code or case.region_code != run.region_code:
            raise PlanningConflict("region_changed")
        if not case.location_confirmed:
            raise PlanningConflict("location_changed")

    open_counts = {
        agent_id: int(db.query(func.count(Investigation.id)).filter(
            Investigation.assigned_agent_id == agent_id,
            Investigation.deleted_at.is_(None),
            Investigation.status.in_(OPEN_STATUSES),
        ).scalar() or 0)
        for agent_id in run.agent_ids
    }
    planned_counts: dict[int, int] = {}
    for item in items:
        if item.outcome == "assigned" and item.agent_id is not None:
            planned_counts[item.agent_id] = planned_counts.get(item.agent_id, 0) + 1
    for agent_id, count in planned_counts.items():
        shift = shift_by_agent.get(agent_id)
        selected_open = sum(
            1 for case in cases
            if case.assigned_agent_id == agent_id and case.status in OPEN_STATUSES
        )
        projected = open_counts.get(agent_id, 0) - selected_open + count
        if shift is None or count > shift.max_visits or projected > shift.max_open_cases:
            raise PlanningConflict("agent_capacity_changed")

    assignments = {
        assignment.investigation_id: assignment
        for assignment in db.query(InvestigationAssignment)
        .filter(InvestigationAssignment.investigation_id.in_(case_ids), InvestigationAssignment.is_active.is_(True))
        .with_for_update()
        .all()
    }
    for item in items:
        if item.outcome != "assigned" or item.agent_id is None:
            continue
        case = case_by_id[item.investigation_id]
        agent = agent_by_id[item.agent_id]
        current = assignments.get(case.id)
        if current and current.agent_id != agent.id:
            raise PlanningConflict("assignment_changed")
        if current is None:
            assignment = InvestigationAssignment(
                investigation_id=case.id,
                agent_id=agent.id,
                assigned_by_id=actor.id,
                assignment_source="automatic",
                note=f"Automatic VROOM planning run {run.id}",
            )
            case.assigned_agent_id = agent.id
            case.status = "assigned"
            db.add(assignment)
            db.flush()
            item.applied_assignment_id = assignment.id
        else:
            item.applied_assignment_id = current.id

        db.add(ActivityLog(
            actor_id=actor.id,
            action="investigation.route_auto_published",
            object_type="investigation",
            object_id=case.id,
            details={"planning_run_id": run.id, "agent_id": agent.id, "sequence": item.sequence},
        ))

    for shift in shifts:
        if shift.agent_id in planned_counts:
            shift.current_planning_run_id = run.id
    run.status = "applied"
    run.applied_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    _log_planning_event(
        "planning.run_applied",
        planning_run_id=run.id,
        work_date=run.work_date.isoformat(),
        region_code=run.region_code,
        assigned_count=sum(1 for item in items if item.outcome == "assigned"),
        unassigned_count=sum(1 for item in items if item.outcome == "unassigned"),
        agent_count=len(planned_counts),
        osrm_dataset=run.osrm_dataset,
    )
    return run

