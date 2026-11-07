from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from math import ceil, cos, isfinite, radians, sqrt
from datetime import date, datetime, timedelta, timezone
from time import monotonic
from zoneinfo import ZoneInfo

import h3

from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session, joinedload

from app.config.settings import OSRM_DATASET_VERSION, PLANNING_MAX_LOCATIONS
from app.models.activity import ActivityLog
from app.models.assignment import InvestigationAssignment
from app.models.investigation import Investigation
from app.models.planning import AgentShift, PlanningItem, PlanningRun, PlanningRoute
from app.models.agent_schedule import AgentWeeklySchedule
from app.models.agent_revisit import AgentRevisitRequest
from app.models.route_event import InvestigationRouteEvent
from app.models.user import User
from app.schemas.planning import LockedAssignment, PlanningRunCreate
from app.services.geospatial import (
    DEFAULT_SERVICE_RADIUS_METRES,
    cells_for_point,
    distance_metres,
    validate_coordinates,
)
from app.services.locations import catalog
from app.services.agent_schedules import ALL_REGIONS, materialize_work_date
from app.services.routing import OSRMClient, RoutingUnavailable, VROOMClient, valid_route_geometry


OPEN_STATUSES = ("assigned", "in_progress", "under_review", "returned_for_correction")
PRIORITY_VALUES = {"normal": 10, "high": 50, "urgent": 100}
ROUTE_RECOVERY_MAX_ATTEMPTS = 3
ROUTE_RECOVERY_BASE_DELAY_SECONDS = 300
PLANNER_LOGIC_VERSION = 10
PRIORITY_SEARCH_LIMIT_SECONDS = 2
ROUTE_RECOVERY_RETRYABLE_ERRORS = {
    # Unknown optimizer exceptions may be transient (for example, a response
    # shape or dependency race). Keep recovery bounded, but do not strand
    # assigned work permanently after one opaque optimizer failure.
    "optimization_failed",
    "planning_disabled",
    "queue_unavailable",
    "osrm_snap_failed",
    "osrm_table_unavailable",
    "osrm_route_unavailable",
    "vroom_unavailable",
    "vroom_solution_duration_invalid",
    "vroom_solution_schedule_invalid",
    "route_geometry_incomplete",
    "auto_route_incomplete",
}
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
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _database_now(db: Session) -> datetime:
    return _as_utc(db.execute(text("SELECT CURRENT_TIMESTAMP")).scalar_one())


def _epoch(value: datetime) -> int:
    return int(_as_utc(value).timestamp())


def _epoch_ceil(value: datetime) -> int:
    """Round lower time-window bounds up to VROOM's whole-second precision."""
    return ceil(_as_utc(value).timestamp())


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
    if values.region_code != ALL_REGIONS and values.region_code not in region_codes:
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
    shift.break_starts_at = _as_utc(values.break_starts_at) if values.break_starts_at else None
    shift.break_ends_at = _as_utc(values.break_ends_at) if values.break_ends_at else None
    shift.source = "manual"
    shift.schedule_version_id = None
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
    else:
        db.flush()
    return shift


def readiness(db: Session, work_date: date, region_code: str, resolution: int) -> dict:
    if resolution not in (7, 8, 9):
        raise PlanningConflict("invalid_h3_resolution")
    if region_code != ALL_REGIONS and region_code not in catalog()["region_codes"]:
        raise PlanningConflict("invalid_region")

    readiness_now = _database_now(db)
    cases = (
        db.query(Investigation)
        .options(joinedload(Investigation.assigned_agent))
        .filter(
            Investigation.deleted_at.is_(None),
            Investigation.region_code.in_(catalog()["region_codes"]) if region_code == ALL_REGIONS else Investigation.region_code == region_code,
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
            or_(AgentShift.region_code == region_code, AgentShift.region_code == ALL_REGIONS) if region_code != ALL_REGIONS else AgentShift.region_code.in_([ALL_REGIONS, *catalog()["region_codes"]]),
            AgentShift.is_available.is_(True),
            AgentShift.shift_ends_at > readiness_now,
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
            "reopen_on": case.reopen_on,
            "region_code": case.region_code,
        }
        for case in all_investigations
        if not (case.location_confirmed and case.latitude is not None and case.longitude is not None)
    ]

    shift_join = and_(
        AgentShift.agent_id == User.id,
        AgentShift.work_date == work_date,
    )
    agent_query = db.query(User, AgentShift).outerjoin(AgentShift, shift_join).filter(User.role == "agent")
    if region_code:
        manual_agent_ids = db.query(InvestigationAssignment.agent_id).join(
            Investigation,
            Investigation.id == InvestigationAssignment.investigation_id,
        ).filter(
            InvestigationAssignment.is_active.is_(True),
            InvestigationAssignment.assignment_source == "manual",
            Investigation.assigned_agent_id == InvestigationAssignment.agent_id,
            Investigation.region_code == region_code,
            Investigation.deleted_at.is_(None),
            Investigation.status.in_(("pending", "assigned", "in_progress")),
        )
        agent_query = agent_query.filter(or_(
            AgentShift.region_code == region_code,
            AgentShift.region_code == ALL_REGIONS,
            User.id.in_(manual_agent_ids),
        ))
    agent_rows = agent_query.order_by(User.name, User.id).all()
    agents = []
    unlocated_agents = []
    for agent, shift in agent_rows:
        has_start = bool(shift and shift.start_latitude is not None and shift.start_longitude is not None)
        if has_start:
            origin_latitude, origin_longitude, origin_label = _route_origin(shift)
            start_point = {"latitude": origin_latitude, "longitude": origin_longitude, "label": origin_label}
        else:
            start_point = None
        agents.append({
            "id": agent.id,
            "name": agent.name,
            "is_active": agent.is_active,
            "region_code": shift.region_code if shift else None,
            "is_available": shift.is_available if shift else None,
            "shift_starts_at": _as_utc(shift.shift_starts_at) if shift else None,
            "shift_ends_at": _as_utc(shift.shift_ends_at) if shift else None,
            "start": start_point,
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
                "reopen_on": case.reopen_on,
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


def _route_origin(shift: AgentShift, now: datetime | None = None) -> tuple[float, float, str | None]:
    now = _as_utc(now or datetime.now(timezone.utc))
    today = now.astimezone(ZoneInfo("Asia/Manila")).date()
    shift_start = _as_utc(shift.shift_starts_at)
    shift_end = _as_utc(shift.shift_ends_at)
    last_completed_at = getattr(shift, "last_completed_at", None)
    last_stop_at = _as_utc(last_completed_at) if last_completed_at else None
    last_attempted_at = getattr(shift, "last_attempted_at", None)
    last_attempt_at = _as_utc(last_attempted_at) if last_attempted_at else None
    reliable_locations = []
    if (
        last_stop_at is not None
        and shift.last_completed_latitude is not None
        and shift.last_completed_longitude is not None
    ):
        reliable_locations.append((last_stop_at, shift.last_completed_latitude, shift.last_completed_longitude, "Latest completed visit (estimated)"))
    if (
        last_attempt_at is not None
        and shift.last_attempted_latitude is not None
        and shift.last_attempted_longitude is not None
    ):
        reliable_locations.append((last_attempt_at, shift.last_attempted_latitude, shift.last_attempted_longitude, "Latest recorded attempt (estimated)"))
    if shift.work_date == today and reliable_locations and shift_start <= max(item[0] for item in reliable_locations) <= now < shift_end:
        _at, latitude, longitude, label = max(reliable_locations, key=lambda item: item[0])
        return latitude, longitude, label
    start_label = shift.start_location_label
    if shift.work_date == today and shift_start <= now < shift_end:
        start_label = f"{start_label or 'Configured starting location'} (assumed; no live location available)"
    return shift.start_latitude, shift.start_longitude, start_label


def _route_destination(shift: AgentShift) -> tuple[float, float, str | None] | None:
    """Return an explicit end point; open routes finish at their last stop."""
    if shift.end_latitude is not None and shift.end_longitude is not None:
        return shift.end_latitude, shift.end_longitude, shift.end_location_label
    return None


def _geometry_prefix_to_location(
    geometry: dict | None,
    latitude: float,
    longitude: float,
) -> dict | None:
    """Clip an estimated saved road line at the nearest point to a reported stop."""
    if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
        return None
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return None
    valid_coordinates = []
    for coordinate in coordinates:
        if (
            not isinstance(coordinate, (list, tuple))
            or len(coordinate) < 2
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                for value in coordinate[:2]
            )
        ):
            return None
        valid_coordinates.append([float(coordinate[0]), float(coordinate[1])])

    longitude_scale = 111_320 * cos(radians(latitude))
    latitude_scale = 111_320
    best_distance_squared = float("inf")
    best_segment_index = -1
    best_point = None
    for index, (start, end) in enumerate(zip(valid_coordinates, valid_coordinates[1:])):
        start_x = (start[0] - longitude) * longitude_scale
        start_y = (start[1] - latitude) * latitude_scale
        delta_x = (end[0] - start[0]) * longitude_scale
        delta_y = (end[1] - start[1]) * latitude_scale
        length_squared = delta_x * delta_x + delta_y * delta_y
        fraction = (
            max(0.0, min(1.0, -(start_x * delta_x + start_y * delta_y) / length_squared))
            if length_squared
            else 0.0
        )
        point = [
            start[0] + fraction * (end[0] - start[0]),
            start[1] + fraction * (end[1] - start[1]),
        ]
        distance_x = (point[0] - longitude) * longitude_scale
        distance_y = (point[1] - latitude) * latitude_scale
        distance_squared = distance_x * distance_x + distance_y * distance_y
        if distance_squared < best_distance_squared:
            best_distance_squared = distance_squared
            best_segment_index = index
            best_point = point

    # Planning rejects locations snapped more than 2 km from a road. Apply the
    # same bound here so unrelated nearby route geometry is never shown as done.
    if best_point is None or best_distance_squared > 2_000 * 2_000:
        return None
    prefix = valid_coordinates[: best_segment_index + 1]
    if (
        not prefix
        or abs(prefix[-1][0] - best_point[0]) > 1e-10
        or abs(prefix[-1][1] - best_point[1]) > 1e-10
    ):
        prefix.append(best_point)
    if len(prefix) < 2:
        return None
    return {"type": "LineString", "coordinates": prefix}


def completed_route_geometry_for_shift(db: Session, shift: AgentShift | None) -> dict | None:
    """Return the prior estimated route prefix ending at this shift's last report."""
    if (
        shift is None
        or shift.last_completed_investigation_id is None
        or shift.last_completed_at is None
        or shift.last_completed_latitude is None
        or shift.last_completed_longitude is None
    ):
        return None

    historical_routes = (
        db.query(PlanningRoute)
        .join(
            PlanningItem,
            and_(
                PlanningItem.planning_run_id == PlanningRoute.planning_run_id,
                PlanningItem.agent_id == PlanningRoute.agent_id,
                PlanningItem.investigation_id == shift.last_completed_investigation_id,
                PlanningItem.outcome == "assigned",
                PlanningItem.sequence.is_not(None),
            ),
        )
        .join(PlanningRun, PlanningRun.id == PlanningRoute.planning_run_id)
        .filter(
            PlanningRoute.agent_id == shift.agent_id,
            PlanningRoute.geometry_status == "ready",
            PlanningRoute.geometry.is_not(None),
            PlanningRun.work_date == shift.work_date,
            PlanningRun.auto_publish.is_(True),
            PlanningRun.status == "applied",
            PlanningRun.created_at <= shift.last_completed_at,
        )
        .order_by(PlanningRun.created_at.desc(), PlanningRun.id.desc())
        .all()
    )
    for route in historical_routes:
        if (
            not valid_route_geometry(route.geometry)
            or not route.geometry_digest
            or _digest(route.geometry) != route.geometry_digest
        ):
            continue
        prefix = _geometry_prefix_to_location(
            route.geometry,
            shift.last_completed_latitude,
            shift.last_completed_longitude,
        )
        if prefix is not None:
            return prefix
    return None


def _planning_floor(shift: AgentShift, now: datetime | None = None) -> datetime:
    now = _as_utc(now or datetime.now(timezone.utc))
    start = _as_utc(shift.shift_starts_at)
    if shift.work_date == now.astimezone(ZoneInfo("Asia/Manila")).date():
        return max(start, now)
    return start


def _reject_vroom_schedule(stage: str, slack_seconds: float | None = None) -> None:
    _log_planning_event(
        "planning.route_schedule_rejected",
        stage=stage,
        slack_seconds=round(slack_seconds, 3) if slack_seconds is not None else None,
    )
    raise RoutingUnavailable("vroom_solution_schedule_invalid")


def _cell_polygon(cell: str) -> dict:
    ring = [[longitude, latitude] for latitude, longitude in h3.cell_to_boundary(cell)]
    return {"type": "Polygon", "coordinates": [ring + [ring[0]]]}


def _build_route_geometries(osrm, case_rows, shifts, outcomes, now: datetime | None = None) -> list[dict]:
    cases = {case.id: case for case in case_rows}
    routes = []
    for shift in shifts:
        stops = sorted([item for item in outcomes.values() if item.get("agent_id") == shift.agent_id and item.get("outcome") == "assigned"], key=lambda item: item["sequence"])
        if not stops:
            continue
        origin_lat, origin_lon, origin_label = _route_origin(shift, now)
        coordinates = [(origin_lat, origin_lon)]
        coordinates.extend((cases[item["investigation_id"]].latitude, cases[item["investigation_id"]].longitude) for item in stops)
        destination = _route_destination(shift)
        if destination is not None:
            end_lat, end_lon, end_label = destination
            coordinates.append((end_lat, end_lon))
            end_point = {"latitude": end_lat, "longitude": end_lon, "label": end_label}
        else:
            last_case = cases[stops[-1]["investigation_id"]]
            end_point = {
                "latitude": last_case.latitude,
                "longitude": last_case.longitude,
                "label": f"Final investigation stop · {last_case.reference_number}",
            }
        route = {"agent_id": shift.agent_id, "start": {"latitude": origin_lat, "longitude": origin_lon, "label": origin_label}, "end": end_point, "geometry_status": "failed", "geometry_error_code": None, "geometry": None, "geometry_digest": None, "total_distance_metres": None, "total_travel_seconds": None,
                 "planned_departure_at": stops[0].get("planned_departure_at"),
                 "total_service_seconds": sum(int(item.get("service_seconds", 0)) for item in stops),
                 "total_waiting_seconds": sum(int(item.get("waiting_seconds", 0)) for item in stops),
                 "total_break_seconds": sum(int(item.get("route_break_seconds", 0)) for item in stops)}
        try:
            result = osrm.route(coordinates)
            route.update(geometry_status="ready", geometry=result["geometry"], geometry_digest=_digest(result["geometry"]), total_distance_metres=round(result["distance"]), total_travel_seconds=round(result["duration"]))
        except RoutingUnavailable as error:
            route["geometry_error_code"] = str(error)
        routes.append(route)
    return routes


def route_response(route: PlanningRoute, agent: User, shift: AgentShift | None = None) -> dict:
    response = {key: getattr(route, key) for key in ("agent_id", "geometry_status", "geometry_error_code", "geometry", "geometry_digest", "total_distance_metres", "total_travel_seconds", "total_service_seconds", "total_waiting_seconds", "total_break_seconds", "planned_departure_at", "start", "end")} | {"agent_name": agent.name, "shift": shift, "total_planned_waiting_seconds": None}
    if not _route_geometry_ready(route):
        response.update(geometry_status="failed", geometry_error_code=route.geometry_error_code or "route_geometry_invalid", geometry=None, geometry_digest=None, total_distance_metres=None, total_travel_seconds=None)
    return response


def route_response_through_last_stop(
    route: PlanningRoute,
    agent: User,
    shift: AgentShift | None,
    ordered_rows: list[tuple[PlanningItem, Investigation]],
) -> dict:
    """Present legacy depot-return geometry as an open route through its last stop."""
    response = route_response(route, agent, shift)
    if ordered_rows:
        # planned_arrival_at marks rows written with VROOM timing; older waiting_seconds
        # values were independently derived gaps and cannot be reported as stop waits.
        timings_known = all(
            item.planned_arrival_at is not None and item.waiting_seconds is not None
            for item, _case in ordered_rows
        )
        planned_waiting = (
            sum(int(item.waiting_seconds) for item, _case in ordered_rows)
            if timings_known else None
        )
        response["total_waiting_seconds"] = planned_waiting
        response["total_planned_waiting_seconds"] = planned_waiting
    if shift is None or _route_destination(shift) is not None or not ordered_rows:
        return response

    _last_item, last_case = ordered_rows[-1]
    response["end"] = {
        "latitude": last_case.latitude,
        "longitude": last_case.longitude,
        "label": f"Final investigation stop · {last_case.reference_number}",
    }
    response["total_distance_metres"] = sum(
        int(item.travel_metres or 0) for item, _case in ordered_rows
    )
    response["total_travel_seconds"] = sum(
        int(item.travel_seconds or 0) for item, _case in ordered_rows
    )
    if response["geometry_status"] == "ready" and response["geometry"]:
        open_geometry = _geometry_prefix_to_location(
            response["geometry"],
            last_case.latitude,
            last_case.longitude,
        )
        if open_geometry is None:
            response.update(
                geometry_status="failed",
                geometry_error_code="route_geometry_cannot_clip_final_stop",
                geometry=None,
                geometry_digest=None,
            )
        else:
            response["geometry"] = open_geometry
            response["geometry_digest"] = _digest(open_geometry)
    return response


def _route_geometry_ready(route: PlanningRoute) -> bool:
    return bool(
        route.geometry_status == "ready" and valid_route_geometry(route.geometry)
        and route.geometry_digest and _digest(route.geometry) == route.geometry_digest
    )


def _active_manual_assignment_owners(db: Session, investigation_ids: list[int] | set[int]) -> dict[int, int]:
    if not investigation_ids:
        return {}
    rows = db.query(
        InvestigationAssignment.investigation_id,
        InvestigationAssignment.agent_id,
    ).filter(
        InvestigationAssignment.investigation_id.in_(investigation_ids),
        InvestigationAssignment.is_active.is_(True),
        InvestigationAssignment.assignment_source == "manual",
    ).all()
    return {investigation_id: agent_id for investigation_id, agent_id in rows}


def _active_automatic_assignment_owners(db: Session, investigation_ids: list[int] | set[int]) -> dict[int, int]:
    if not investigation_ids:
        return {}
    rows = db.query(
        InvestigationAssignment.investigation_id,
        InvestigationAssignment.agent_id,
    ).filter(
        InvestigationAssignment.investigation_id.in_(investigation_ids),
        InvestigationAssignment.is_active.is_(True),
        InvestigationAssignment.assignment_source == "automatic",
    ).all()
    return {investigation_id: agent_id for investigation_id, agent_id in rows}


def _route_assignment_blocker(
    case: Investigation,
    region_code: str,
    manual_owner_agent_id: int | None = None,
) -> str | None:
    if (
        region_code != ALL_REGIONS
        and case.region_code != region_code
        and manual_owner_agent_id != case.assigned_agent_id
    ):
        return "region_mismatch"
    if case.location_confirmed_at is None:
        return "location_unconfirmed"
    if case.latitude is None or case.longitude is None:
        return "location_coordinates_missing"
    return None


def _case_within_service_radius(case: Investigation, shift: AgentShift) -> bool:
    if (
        case.latitude is None or case.longitude is None
        or shift.start_latitude is None or shift.start_longitude is None
    ):
        return False
    try:
        return distance_metres(
            shift.start_latitude,
            shift.start_longitude,
            case.latitude,
            case.longitude,
        ) <= DEFAULT_SERVICE_RADIUS_METRES
    except ValueError:
        return False


def _shift_has_valid_depot(shift: AgentShift) -> bool:
    if shift.start_latitude is None or shift.start_longitude is None:
        return False
    try:
        validate_coordinates(shift.start_latitude, shift.start_longitude)
        return True
    except ValueError:
        return False


def planning_route_overview(db: Session, work_date: date, region_code: str | None = None) -> dict:
    """Return current assignment-driven routes, never a route for a stale stop set."""
    if region_code and region_code not in catalog()["region_codes"]:
        raise PlanningConflict("invalid_region")
    overview_now = _database_now(db)

    query = db.query(User, AgentShift).outerjoin(
        AgentShift,
        and_(AgentShift.agent_id == User.id, AgentShift.work_date == work_date),
    ).filter(User.role == "agent")
    if region_code:
        manual_agent_ids = db.query(InvestigationAssignment.agent_id).join(
            Investigation,
            Investigation.id == InvestigationAssignment.investigation_id,
        ).filter(
            InvestigationAssignment.is_active.is_(True),
            InvestigationAssignment.assignment_source == "manual",
            Investigation.assigned_agent_id == InvestigationAssignment.agent_id,
            Investigation.region_code == region_code,
            Investigation.deleted_at.is_(None),
            Investigation.status.in_(("pending", "assigned", "in_progress")),
        )
        query = query.filter(or_(
            AgentShift.region_code == region_code,
            AgentShift.region_code == ALL_REGIONS,
            User.id.in_(manual_agent_ids),
        ))
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
        auto_runs = [run for run in auto_runs if run.region_code in {region_code, ALL_REGIONS}]
    latest_auto_run_by_agent = {}
    for run in auto_runs:
        for agent_id in run.agent_ids or []:
            if agent_id in agent_ids and agent_id not in latest_auto_run_by_agent:
                latest_auto_run_by_agent[agent_id] = run

    cases = db.query(Investigation).filter(
        Investigation.assigned_agent_id.in_(agent_ids),
        Investigation.deleted_at.is_(None),
        Investigation.status.in_(("pending", "assigned", "in_progress")),
    ).order_by(Investigation.id).all() if agent_ids else []
    manual_owners = _active_manual_assignment_owners(db, {case.id for case in cases})
    automatic_owners = _active_automatic_assignment_owners(db, {case.id for case in cases})
    current_ids_by_agent: dict[int, set[int]] = {agent_id: set() for agent_id in agent_ids}
    route_warnings_by_agent: dict[int, list[dict]] = {agent_id: [] for agent_id in agent_ids}
    for case in cases:
        shift = shifts.get(case.assigned_agent_id)
        if shift is None or not shift.is_available:
            route_warnings_by_agent[case.assigned_agent_id].append({
                "investigation_id": case.id,
                "reference_number": case.reference_number,
                "reason": "agent_shift_ended"
                if shift and _as_utc(shift.shift_ends_at) <= overview_now
                else "agent_shift_unavailable_today",
            })
            continue
        blocker = _route_assignment_blocker(case, shift.region_code, manual_owners.get(case.id))
        if blocker:
            route_warnings_by_agent[case.assigned_agent_id].append({
                "investigation_id": case.id,
                "reference_number": case.reference_number,
                "reason": blocker,
            })
        elif (
            automatic_owners.get(case.id) == case.assigned_agent_id
            and not _case_within_service_radius(case, shift)
        ):
            route_warnings_by_agent[case.assigned_agent_id].append({
                "investigation_id": case.id,
                "reference_number": case.reference_number,
                "reason": "outside_service_radius",
            })
        else:
            if shift.current_planning_run_id is not None:
                unscheduled_item = db.query(PlanningItem).filter(
                    PlanningItem.planning_run_id == shift.current_planning_run_id,
                    PlanningItem.investigation_id == case.id,
                    PlanningItem.outcome == "unassigned",
                ).first()
                if unscheduled_item is not None:
                    route_warnings_by_agent[case.assigned_agent_id].append({
                        "investigation_id": case.id,
                        "reference_number": case.reference_number,
                        "reason": unscheduled_item.reason or "no_feasible_route_under_constraints",
                    })
                    continue
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
        planning_warnings = route_warnings_by_agent.get(agent.id, [])
        exact_current_route = bool(
            shift
            and shift.is_available
            and run
            and (run.region_code == ALL_REGIONS or run.region_code == shift.region_code)
            and route_model
            and route_case_ids == stored_case_ids
            and expected_case_ids == route_case_ids
        )
        priority_order_warnings = [
            {
                "investigation_id": warning["investigation_id"],
                "reference_number": warning["reference_number"],
                "deferred_investigation_id": warning["deferred_investigation_id"],
                "deferred_reference_number": warning["deferred_reference_number"],
                "reason": warning["reason"],
            }
            for warning in (run.warnings or [])
            if exact_current_route
            and warning.get("type") == "priority_order"
            and warning.get("agent_id") == agent.id
        ] if run else []

        route = None
        stops = []
        if exact_current_route and route_model and route_agent and shift:
            ordered_route_items = sorted(
                route_items,
                key=lambda row: (row[0].sequence or 0, row[1].id),
            )
            route = route_response_through_last_stop(
                route_model,
                route_agent,
                shift,
                ordered_route_items,
            )
            stops = [
                {
                    "service_duration_seconds": case.service_duration_seconds,
                    "investigation_id": case.id,
                    "reference_number": case.reference_number,
                    "address_display": case.address_display,
                    "sequence": item.sequence,
                    "estimated_arrival_at": item.estimated_arrival_at,
                    "earliest_arrival_estimate_at": item.estimated_arrival_at,
                    "planned_arrival_at": item.planned_arrival_at,
                    "estimated_service_start_at": item.estimated_service_start_at,
                    "waiting_seconds": item.waiting_seconds if item.planned_arrival_at is not None else None,
                    "planned_waiting_seconds": item.waiting_seconds if item.planned_arrival_at is not None else None,
                    "travel_seconds": item.travel_seconds,
                    "travel_metres": item.travel_metres,
                    "latitude": case.latitude,
                    "longitude": case.longitude,
                    "priority": case.priority,
                    "status": case.status,
                }
                for item, case in ordered_route_items
            ]

        if route is not None and route["geometry_status"] == "ready":
            route_status = "partially_published" if planning_warnings else "published"
        elif route is not None:
            route_status = "failed"
        elif refresh is not None and refresh.auto_route_status in {
            "queued", "running", "failed", "partially_published", "unscheduled",
        }:
            route_status = refresh.auto_route_status
        elif planning_run and planning_run.status in {"queued", "running", "ready"}:
            route_status = "queued" if planning_run.status == "queued" else "running"
        elif planning_run and planning_run.status == "failed":
            route_status = "failed"
        elif expected_case_ids or planning_warnings:
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
            "planning_warnings": planning_warnings,
            "priority_order_warnings": priority_order_warnings,
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
            "completed_route_geometry": completed_route_geometry_for_shift(db, shift),
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
    available_shifts = db.query(AgentShift).join(
        User, User.id == AgentShift.agent_id,
    ).filter(
        AgentShift.work_date == work_date,
        AgentShift.is_available.is_(True),
        AgentShift.shift_ends_at > _database_now(db),
        User.role == "agent",
        User.is_active.is_(True),
    ).all()
    active_assignments = db.query(InvestigationAssignment).filter(
        InvestigationAssignment.investigation_id.in_(case_ids),
        InvestigationAssignment.is_active.is_(True),
    ).all() if case_ids else []
    assignment_by_case = {item.investigation_id: item for item in active_assignments}

    runs_query = db.query(PlanningRun).filter(
        PlanningRun.work_date == work_date,
        PlanningRun.auto_publish.is_(True),
    )
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
        elif case.manual_assignment_required:
            state, reason = "unassigned", "manual_assignment_required"
        elif not case.location_confirmed:
            state, reason = "pending", "location_unconfirmed"
        elif run and run.status in {"queued", "running", "ready"}:
            state, reason = "optimizing", None
        elif run and run.status == "failed":
            state, reason = "failed", run.error_code or "optimization_failed"
        elif run and run.status == "applied" and item and item.outcome == "unassigned":
            state, reason = "unassigned", item.reason
        elif case.assigned_agent_id is None and case.location_confirmed and case.latitude is not None and case.longitude is not None:
            region_shifts = [
                shift for shift in available_shifts
                if shift.region_code in {case.region_code, ALL_REGIONS}
            ]
            if not region_shifts:
                state, reason = "unassigned", "no_available_agents"
            elif not any(_shift_has_valid_depot(shift) for shift in region_shifts):
                state, reason = "unassigned", "no_routable_agent_start"
            elif not any(_case_within_service_radius(case, shift) for shift in region_shifts):
                state, reason = "unassigned", "outside_service_radius"
            else:
                state, reason = "pending", None
        else:
            state, reason = "pending", None
        routing_status = "pending"
        routing_reason = None
        if assignment and run and run.status == "applied" and item:
            if (
                item.outcome == "unassigned"
                and item.agent_id is None
            ):
                routing_status = "unscheduled"
                routing_reason = item.reason or "no_feasible_route_under_constraints"
            elif (
                item.outcome == "assigned"
                and item.agent_id == assignment.agent_id
                and db.query(PlanningRoute.id).filter(
                    PlanningRoute.planning_run_id == run.id,
                    PlanningRoute.agent_id == assignment.agent_id,
                    PlanningRoute.geometry_status == "ready",
                ).first() is not None
            ):
                routing_status = "scheduled"
            else:
                routing_reason = item.reason or "route_not_published"
        if assignment and assignment.auto_route_work_date == work_date:
            if assignment.auto_route_status == "unscheduled":
                routing_status = "unscheduled"
                routing_reason = next(iter(assignment.auto_route_errors or []), None)
            elif assignment.auto_route_status in {"queued", "running"}:
                routing_status = "pending"
                routing_reason = "route_refresh_pending"
        investigation_states.append({
            "investigation_id": case.id,
            "planning_status": state,
            "reason": reason,
            "planning_run_id": run.id if run else None,
            "assignment_source": assignment.assignment_source if assignment else None,
            "routing_status": routing_status,
            "routing_reason": routing_reason,
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
        if agent["route_status"] in {"published", "partially_published"}
        and agent["route"] is not None
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
    if request.region_code != ALL_REGIONS and request.region_code not in catalog()["region_codes"]:
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
        if request.region_code == ALL_REGIONS:
            if shift.region_code != ALL_REGIONS and shift.region_code not in catalog()["region_codes"]:
                raise PlanningConflict("agent_region_mismatch")
        elif shift.region_code not in {request.region_code, ALL_REGIONS}:
            raise PlanningConflict("agent_region_mismatch")
    case_ids = set(request.investigation_ids)
    locked = {item.investigation_id: item.agent_id for item in request.locked_assignments}
    movable_case_ids = set(getattr(request, "movable_investigation_ids", []))
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
            if item.investigation_id not in movable_case_ids:
                locked[item.investigation_id] = shift.agent_id

    if len(case_ids) > 80:
        raise PlanningConflict("run_too_large")
    cases = db.query(Investigation).filter(Investigation.id.in_(sorted(case_ids))).order_by(Investigation.id).all()
    if len(cases) != len(case_ids):
        raise PlanningConflict("investigation_not_found")
    manual_owners = _active_manual_assignment_owners(db, {case.id for case in cases})
    case_coordinates = set()
    for case in cases:
        if case.deleted_at is not None or case.status not in {"pending", "assigned"}:
            raise PlanningConflict("investigation_not_assignable")
        if case.manual_assignment_required and case.assigned_agent_id is None:
            raise PlanningConflict("manual_assignment_required")
        fixed_agent = locked.get(case.id) or (None if case.id in set(getattr(request, "movable_investigation_ids", [])) else case.assigned_agent_id)
        manual_override = manual_owners.get(case.id) == fixed_agent == case.assigned_agent_id
        if request.region_code != ALL_REGIONS and case.region_code != request.region_code and not manual_override:
            raise PlanningConflict("investigation_region_mismatch")
        if not case.location_confirmed:
            raise PlanningConflict("location_unconfirmed")
        if fixed_agent is not None and fixed_agent not in request.agent_ids:
            raise PlanningConflict("locked_agent_not_selected")
        case_coordinates.add((round(case.latitude, 6), round(case.longitude, 6)))
    for shift in shifts:
        origin_latitude, origin_longitude, _origin_label = _route_origin(shift)
        case_coordinates.add((round(origin_latitude, 6), round(origin_longitude, 6)))
        destination = _route_destination(shift)
        if destination is not None:
            end_lat, end_lon, _end_label = destination
            case_coordinates.add((round(end_lat, 6), round(end_lon, 6)))
    if len(case_coordinates) > min(80, PLANNING_MAX_LOCATIONS):
        raise PlanningConflict("run_too_large")

    run = PlanningRun(
        requested_by_id=requester.id,
        work_date=request.work_date,
        region_code=request.region_code,
        investigation_ids=sorted(case_ids),
        agent_ids=request.agent_ids,
        locked_assignments=[{"investigation_id": key, "agent_id": value} for key, value in sorted(locked.items())],
        movable_investigation_ids=sorted(set(getattr(request, "movable_investigation_ids", []))),
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
    explicit_assignment_ids = run.auto_assignment_ids or ([run.auto_assignment_id] if run.auto_assignment_id else [])
    current_assignment_ids = db.query(InvestigationAssignment.id).join(
        Investigation, Investigation.id == InvestigationAssignment.investigation_id,
    ).filter(
        InvestigationAssignment.is_active.is_(True),
        Investigation.id.in_(run.investigation_ids or []),
        Investigation.assigned_agent_id == InvestigationAssignment.agent_id,
    ).all() if run.investigation_ids else []
    assignment_ids = list(dict.fromkeys([
        *explicit_assignment_ids,
        *(assignment_id for (assignment_id,) in current_assignment_ids),
    ]))
    explicit_ids = set(explicit_assignment_ids)
    for assignment_id in assignment_ids:
        assignment = db.get(InvestigationAssignment, assignment_id)
        if assignment is None:
            continue
        assignment.auto_route_work_date = run.work_date
        if assignment_id in explicit_ids:
            assignment.auto_route_run_ids = list(dict.fromkeys([*(assignment.auto_route_run_ids or []), run.id]))[-20:]
        else:
            # Background reconciliation is a new current attempt, not an
            # unbounded history of every five-minute retry.
            assignment.auto_route_run_ids = [run.id]
        assignment.auto_route_agent_ids = list(dict.fromkeys([*(assignment.auto_route_agent_ids or []), *(run.agent_ids or [])]))
        assignment.auto_route_errors = []
        if run.status == "failed":
            assignment.auto_route_errors = [run.error_code or "automatic_planning_failed"]
            assignment.auto_route_status = "failed"
        else:
            assignment.auto_route_status = "running" if run.status in {"running", "ready"} else "queued"


def _automatic_assignments_requiring_replan(
    db: Session,
    region_code: str,
    available_agent_ids: set[int],
    work_date: date,
    *,
    include_outside_roster: bool,
) -> list[tuple[InvestigationAssignment, Investigation]]:
    """Return automatic work that violates today's radius or roster constraints."""
    assignments = (
        db.query(InvestigationAssignment, Investigation)
        .join(Investigation, Investigation.id == InvestigationAssignment.investigation_id)
        .filter(
            InvestigationAssignment.is_active.is_(True),
            InvestigationAssignment.assignment_source == "automatic",
            Investigation.assigned_agent_id == InvestigationAssignment.agent_id,
            Investigation.deleted_at.is_(None),
            Investigation.status.in_(("pending", "assigned")),
            Investigation.location_confirmed_at.is_not(None),
            Investigation.latitude.is_not(None),
            Investigation.longitude.is_not(None),
            Investigation.region_code.in_(catalog()["region_codes"]) if region_code == ALL_REGIONS else Investigation.region_code == region_code,
        )
        .order_by(InvestigationAssignment.assigned_at, Investigation.id)
        .all()
    )
    owner_ids = {assignment.agent_id for assignment, _case in assignments}
    owner_shifts = {
        shift.agent_id: shift
        for shift in db.query(AgentShift).filter(
            AgentShift.work_date == work_date,
            AgentShift.agent_id.in_(owner_ids),
        ).all()
    } if owner_ids else {}
    return [
        (assignment, case)
        for assignment, case in assignments
        if (
            (owner_shift := owner_shifts.get(assignment.agent_id)) is not None
            and not _case_within_service_radius(case, owner_shift)
        ) or (
            include_outside_roster
            and case.assigned_agent_id not in available_agent_ids
        )
    ]


def queue_automatic_planning(
    db: Session,
    region_code: str,
    requester: User,
    work_date: date | None = None,
    *,
    auto_assignment_id: int | None = None,
    auto_assignment_ids: list[int] | None = None,
    exclude_investigation_ids: set[int] | None = None,
    require_missing_route: bool = False,
) -> PlanningRun | None:
    """Coalesce a regional planning trigger and enqueue one VROOM run.

    Assignments owned by agents on the current roster are carried as locked
    jobs. During missing-route recovery, automatic assignments whose owners
    lack an eligible shift are offered as movable jobs; manual assignments stay
    with their owners. Other assigned cases remain untouched and are recorded
    as blockers. Confirmed, unassigned pending cases are also offered for new
    assignment. H3 orders the bounded batch; OSRM/VROOM choose routes and agents.
    """
    planning_now = _database_now(db)
    work_date = work_date or planning_now.astimezone(ZoneInfo("Asia/Manila")).date()
    if region_code != ALL_REGIONS and region_code not in catalog()["region_codes"]:
        raise PlanningConflict("invalid_region")
    if work_date == planning_now.astimezone(ZoneInfo("Asia/Manila")).date():
        materialize_work_date(db, work_date)
    all_regions_available = db.query(AgentShift.id).join(
        User, User.id == AgentShift.agent_id,
    ).filter(
        AgentShift.work_date == work_date,
        AgentShift.region_code == ALL_REGIONS,
        AgentShift.is_available.is_(True),
        AgentShift.shift_ends_at > planning_now,
        User.role == "agent",
        User.is_active.is_(True),
    ).first() is not None
    region_code = ALL_REGIONS if region_code == ALL_REGIONS or all_regions_available else region_code
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
    if region_code == ALL_REGIONS:
        db.query(PlanningRun).filter(
            PlanningRun.work_date == work_date,
            PlanningRun.region_code != ALL_REGIONS,
            PlanningRun.auto_publish.is_(True),
            PlanningRun.status.in_(("queued", "running", "ready")),
        ).update(
            {PlanningRun.status: "stale", PlanningRun.error_code: "global_scope_superseded"},
            synchronize_session=False,
        )
    shift_rows = (
        db.query(AgentShift, User)
        .join(User, User.id == AgentShift.agent_id)
        .filter(
            AgentShift.work_date == work_date,
            or_(AgentShift.region_code == region_code, AgentShift.region_code == ALL_REGIONS) if region_code != ALL_REGIONS else AgentShift.region_code.in_([ALL_REGIONS, *catalog()["region_codes"]]),
            AgentShift.is_available.is_(True),
            AgentShift.shift_ends_at > planning_now,
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
    movable_auto_assignments = _automatic_assignments_requiring_replan(
        db,
        region_code,
        set(requested_agent_ids),
        work_date,
        include_outside_roster=require_missing_route and bool(requested_agent_ids),
    )
    movable_auto_cases = [case for _assignment, case in movable_auto_assignments]
    movable_ids = {case.id for case in movable_auto_cases}
    tracking_assignment_ids = list(dict.fromkeys([
        *tracking_assignment_ids,
        *(assignment.id for assignment, _case in movable_auto_assignments),
    ]))

    all_open_assigned = db.query(Investigation).filter(
        Investigation.assigned_agent_id.in_(requested_agent_ids),
        Investigation.deleted_at.is_(None),
        Investigation.status.in_(("pending", "assigned")),
    ).order_by(Investigation.id).all() if requested_agent_ids else []
    manual_owners = _active_manual_assignment_owners(db, {case.id for case in all_open_assigned})
    assigned_by_agent: dict[int, list[Investigation]] = {}
    for case in all_open_assigned:
        assigned_by_agent.setdefault(case.assigned_agent_id, []).append(case)

    # Keep the entire available shift roster. Valid assigned investigations in
    # this scope stay locked to their current agents; bad or out-of-scope
    # assignments are recorded as blockers instead of making the agent
    # unavailable for every other valid stop.
    eligible_agent_ids = requested_agent_ids
    eligible_shifts = [shifts_by_agent[agent_id] for agent_id in eligible_agent_ids]
    assignment_warnings = [
        {
            "type": "blocked_assigned_investigation",
            "agent_id": agent_id,
            "investigation_id": case.id,
            "reference_number": case.reference_number,
            "reason": blocker,
        }
        for agent_id in requested_agent_ids
        for case in assigned_by_agent.get(agent_id, [])
        if (blocker := _route_assignment_blocker(case, region_code, manual_owners.get(case.id))) is not None
    ]
    locked_cases = [
        case
        for agent_id in eligible_agent_ids
        for case in assigned_by_agent.get(agent_id, [])
        if case.id not in movable_ids
        and _route_assignment_blocker(case, region_code, manual_owners.get(case.id)) is None
    ]
    scope_cases = db.query(Investigation)
    if region_code != ALL_REGIONS:
        scope_cases = scope_cases.filter(Investigation.region_code == region_code)
    else:
        scope_cases = scope_cases.filter(Investigation.region_code.in_(catalog()["region_codes"]))
    candidates = [] if require_missing_route else scope_cases.filter(
        Investigation.deleted_at.is_(None),
        Investigation.status == "pending",
        Investigation.assigned_agent_id.is_(None),
        Investigation.manual_assignment_required.is_(False),
        Investigation.location_confirmed_at.is_not(None),
        Investigation.latitude.is_not(None),
        Investigation.longitude.is_not(None),
    ).order_by(Investigation.h3_r7, Investigation.h3_r8, Investigation.id).all()
    excluded_ids = exclude_investigation_ids or set()
    candidates = [case for case in candidates if case.id not in excluded_ids]
    candidates = [
        case for case in candidates
        if any(
            shift.region_code in {case.region_code, ALL_REGIONS}
            and _case_within_service_radius(case, shift)
            for shift in eligible_shifts
        )
    ]

    # Manual work stays with its assigned agent. Existing automatic work that
    # exceeds the depot radius re-enters planning; recovery can also move work
    # from an owner who has no eligible shift.
    if require_missing_route:
        missing_route_ids = _missing_route_assigned_case_ids(db, work_date, region_code)
        if not missing_route_ids:
            db.commit()
            return None
        # A queued or running run already owns this scope. Leave its captured
        # inputs intact; the worker will publish it or mark it stale, and the
            # next reconciliation pass can recover changed inputs.
        active_recovery_run = (
            db.query(PlanningRun)
            .filter(
                PlanningRun.work_date == work_date,
                PlanningRun.region_code == region_code,
                PlanningRun.auto_publish.is_(True),
                PlanningRun.status.in_(("queued", "running", "ready")),
            )
            .order_by(PlanningRun.id.desc())
            .with_for_update()
            .first()
        )
        if active_recovery_run is not None:
            db.commit()
            return active_recovery_run
    locked_assignments = [
        LockedAssignment(investigation_id=case.id, agent_id=case.assigned_agent_id)
        for case in locked_cases
        if case.assigned_agent_id in eligible_agent_ids
    ]
    locked_assignment_payload = [
        {"investigation_id": item.investigation_id, "agent_id": item.agent_id}
        for item in locked_assignments
    ]

    # H3 provides a stable geographic batching order; it never chooses a vehicle.
    selected_cases = list(locked_cases) + movable_auto_cases
    selected_ids = {case.id for case in selected_cases}
    coordinates = {
        (round(_route_origin(shift)[0], 6), round(_route_origin(shift)[1], 6))
        for shift in eligible_shifts
    }
    for shift in eligible_shifts:
        destination = _route_destination(shift)
        if destination is not None:
            end_lat, end_lon, _end_label = destination
            coordinates.add((round(end_lat, 6), round(end_lon, 6)))
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
    investigation_ids = sorted(selected_ids)

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
            run.warnings = assignment_warnings
            run.locked_assignments = locked_assignment_payload
            run.movable_investigation_ids = sorted(movable_ids)
            cases_for_digest = selected_cases
            run.input_digest = _digest(_snapshot(db, run, cases_for_digest, eligible_shifts, [agents_by_id[key] for key in eligible_agent_ids]))
            run.auto_replan_requested = run.auto_replan_requested or bool(overflow and selected_candidate_ids)
        else:
            current_input_digest = _digest(
                _snapshot(
                    db,
                    run,
                    selected_cases,
                    eligible_shifts,
                    [agents_by_id[key] for key in eligible_agent_ids],
                )
            )
            if (
                set(investigation_ids) != existing_ids
                or set(eligible_agent_ids) != set(run.agent_ids or [])
                or locked_assignment_payload != (run.locked_assignments or [])
                or movable_ids != set(run.movable_investigation_ids or [])
                or (run.input_digest is not None and current_input_digest != run.input_digest)
                or overflow
            ):
                run.auto_replan_requested = True
            run.warnings = [
                warning for warning in (run.warnings or [])
                if warning.get("type") != "blocked_assigned_investigation"
            ] + assignment_warnings
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
        movable_investigation_ids=sorted(movable_ids),
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
            movable_investigation_ids=sorted(movable_ids),
            auto_publish=True,
            auto_assignment_id=auto_assignment_id,
            auto_assignment_ids=tracking_assignment_ids,
            status="failed",
            error_code=str(error) or "planning_scope_invalid",
            warnings=assignment_warnings,
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
    run.movable_investigation_ids = sorted(movable_ids)
    run.warnings = assignment_warnings
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


def _missing_route_assigned_case_ids(db: Session, work_date: date, region_code: str) -> set[int]:
    now = _database_now(db)
    agent_ids = [
        agent_id
        for (agent_id,) in db.query(AgentShift.agent_id)
        .join(User, User.id == AgentShift.agent_id)
        .filter(
            AgentShift.work_date == work_date,
            or_(AgentShift.region_code == region_code, AgentShift.region_code == ALL_REGIONS) if region_code != ALL_REGIONS else AgentShift.region_code.in_([ALL_REGIONS, *catalog()["region_codes"]]),
            AgentShift.is_available.is_(True),
            AgentShift.shift_ends_at > now,
            User.role == "agent",
            User.is_active.is_(True),
        )
        .order_by(AgentShift.agent_id)
        .all()
    ]
    eligible_cases = db.query(Investigation).filter(
        Investigation.assigned_agent_id.in_(agent_ids),
        Investigation.region_code.in_(catalog()["region_codes"]) if region_code == ALL_REGIONS else Investigation.region_code == region_code,
        Investigation.deleted_at.is_(None),
        Investigation.status.in_(("pending", "assigned")),
        Investigation.location_confirmed_at.is_not(None),
        Investigation.latitude.is_not(None),
        Investigation.longitude.is_not(None),
    ).order_by(Investigation.id).all()
    manual_cases = db.query(Investigation).join(
        InvestigationAssignment,
        and_(
            InvestigationAssignment.investigation_id == Investigation.id,
            InvestigationAssignment.agent_id == Investigation.assigned_agent_id,
        ),
    ).filter(
        Investigation.assigned_agent_id.in_(agent_ids),
        InvestigationAssignment.is_active.is_(True),
        InvestigationAssignment.assignment_source == "manual",
        Investigation.deleted_at.is_(None),
        Investigation.status.in_(("pending", "assigned")),
        Investigation.location_confirmed_at.is_not(None),
        Investigation.latitude.is_not(None),
        Investigation.longitude.is_not(None),
    ).order_by(Investigation.id).all()
    movable_auto_assignments = _automatic_assignments_requiring_replan(
        db, region_code, set(agent_ids), work_date, include_outside_roster=bool(agent_ids),
    )
    movable_auto_cases = [case for _assignment, case in movable_auto_assignments]
    movable_auto_ids = {case.id for case in movable_auto_cases}
    eligible_cases_by_id = {case.id: case for case in eligible_cases}
    eligible_cases_by_id.update({case.id: case for case in manual_cases})
    eligible_cases_by_id.update({case.id: case for case in movable_auto_cases})
    eligible_cases = list(eligible_cases_by_id.values())
    if not eligible_cases:
        return set()

    overview = planning_route_overview(db, work_date, None if region_code == ALL_REGIONS else region_code)
    overview_by_agent = {item["id"]: item for item in overview["agents"]}
    shifts_by_agent = {
        shift.agent_id: shift
        for shift in db.query(AgentShift).filter(
            AgentShift.agent_id.in_(agent_ids),
            AgentShift.work_date == work_date,
        ).all()
    } if agent_ids else {}
    missing_case_ids: set[int] = set()
    for case in eligible_cases:
        if case.id in movable_auto_ids:
            missing_case_ids.add(case.id)
            continue
        item = overview_by_agent.get(case.assigned_agent_id)
        shift = shifts_by_agent.get(case.assigned_agent_id)
        current_item = db.query(PlanningItem).filter(
            PlanningItem.planning_run_id == shift.current_planning_run_id if shift and shift.current_planning_run_id else PlanningItem.id == -1,
            PlanningItem.investigation_id == case.id,
            PlanningItem.outcome == "unassigned",
            PlanningItem.reason.in_(("manual_stop_exceeds_shift", "no_feasible_route_under_constraints")),
        ).first()
        if current_item is not None:
            continue
        route = item.get("route") if item else None
        routed_ids = {
            stop["investigation_id"] for stop in (item.get("stops", []) if item else [])
        }
        if (
            route is None
            or route.get("geometry_status") != "ready"
            or case.id not in routed_ids
        ):
            missing_case_ids.add(case.id)
    return missing_case_ids


def _recovery_inputs_changed(
    db: Session,
    run: PlanningRun,
    current_assigned_case_ids: set[int],
) -> bool:
    locked_case_ids = {
        item.get("investigation_id")
        for item in (run.locked_assignments or [])
        if isinstance(item, dict)
    }
    captured_assigned_case_ids = locked_case_ids | set(run.movable_investigation_ids or [])
    if current_assigned_case_ids != captured_assigned_case_ids:
        return True

    now = _database_now(db)
    current_agent_ids = {
        agent_id
        for (agent_id,) in db.query(AgentShift.agent_id)
        .join(User, User.id == AgentShift.agent_id)
        .filter(
            AgentShift.work_date == run.work_date,
            or_(AgentShift.region_code == run.region_code, AgentShift.region_code == ALL_REGIONS) if run.region_code != ALL_REGIONS else AgentShift.region_code.in_([ALL_REGIONS, *catalog()["region_codes"]]),
            AgentShift.is_available.is_(True),
            AgentShift.shift_ends_at > now,
            User.role == "agent",
            User.is_active.is_(True),
        )
        .all()
    }
    if current_agent_ids != set(run.agent_ids or []):
        return True

    if not run.input_digest:
        return False
    cases = db.query(Investigation).filter(
        Investigation.id.in_(run.investigation_ids or [])
    ).order_by(Investigation.id).all() if run.investigation_ids else []
    shifts = db.query(AgentShift).filter(
        AgentShift.agent_id.in_(run.agent_ids or []),
        AgentShift.work_date == run.work_date,
    ).order_by(AgentShift.agent_id).all() if run.agent_ids else []
    agents = db.query(User).filter(
        User.id.in_(run.agent_ids or [])
    ).order_by(User.id).all() if run.agent_ids else []
    return _digest(_snapshot(db, run, cases, shifts, agents)) != run.input_digest


def reconcile_missing_route_scopes(db: Session, work_date: date | None = None) -> dict[str, int | str]:
    """Queue recovery for eligible assigned work that lacks a current route.

    This is called by the periodic Celery task. It only examines today's
    available shifts, relies on the route overview's exact-stop validation,
    and delegates all planning and publication to the existing queue/worker.
    """
    planning_now = _database_now(db)
    today = planning_now.astimezone(ZoneInfo("Asia/Manila")).date()
    work_date = work_date or today
    if work_date == today:
        materialize_work_date(db, work_date)
    shift_rows = (
        db.query(AgentShift.region_code, AgentShift.agent_id)
        .join(User, User.id == AgentShift.agent_id)
        .filter(
            AgentShift.work_date == work_date,
            AgentShift.is_available.is_(True),
            AgentShift.shift_ends_at > planning_now,
            User.role == "agent",
            User.is_active.is_(True),
        )
        .order_by(AgentShift.region_code, AgentShift.agent_id)
        .all()
    )
    agent_ids_by_region: dict[str, list[int]] = {}
    if any(region_code == ALL_REGIONS for region_code, _agent_id in shift_rows):
        agent_ids_by_region[ALL_REGIONS] = sorted({agent_id for _region_code, agent_id in shift_rows})
    else:
        for region_code, agent_id in shift_rows:
            agent_ids_by_region.setdefault(region_code, []).append(agent_id)

    if ALL_REGIONS not in agent_ids_by_region:
        automatic_assignment_regions = {
            region_code
            for (region_code,) in db.query(Investigation.region_code).join(
                InvestigationAssignment,
                and_(
                    InvestigationAssignment.investigation_id == Investigation.id,
                    InvestigationAssignment.agent_id == Investigation.assigned_agent_id,
                ),
            ).filter(
                InvestigationAssignment.is_active.is_(True),
                InvestigationAssignment.assignment_source == "automatic",
                Investigation.deleted_at.is_(None),
                Investigation.status.in_(("pending", "assigned")),
                Investigation.location_confirmed_at.is_not(None),
                Investigation.latitude.is_not(None),
                Investigation.longitude.is_not(None),
            ).distinct().all()
        }
        for assignment_region in automatic_assignment_regions:
            if assignment_region in agent_ids_by_region:
                continue
            if _automatic_assignments_requiring_replan(
                db,
                assignment_region,
                set(),
                work_date,
                include_outside_roster=False,
            ):
                agent_ids_by_region[assignment_region] = []

    attempted = 0
    skipped_no_eligible_work = 0
    skipped_retry_limit = 0
    skipped_backoff = 0
    skipped_permanent_failure = 0
    now = datetime.now(timezone.utc)

    for region_code, agent_ids in agent_ids_by_region.items():
        eligible_cases = (
            db.query(Investigation)
            .filter(
                Investigation.assigned_agent_id.in_(agent_ids),
                Investigation.region_code.in_(catalog()["region_codes"]) if region_code == ALL_REGIONS else Investigation.region_code == region_code,
                Investigation.deleted_at.is_(None),
                Investigation.status.in_(("pending", "assigned")),
                Investigation.location_confirmed_at.is_not(None),
                Investigation.latitude.is_not(None),
                Investigation.longitude.is_not(None),
            )
            .order_by(Investigation.id)
            .all()
        )
        manual_cases = db.query(Investigation).join(
            InvestigationAssignment,
            and_(
                InvestigationAssignment.investigation_id == Investigation.id,
                InvestigationAssignment.agent_id == Investigation.assigned_agent_id,
            ),
        ).filter(
            Investigation.assigned_agent_id.in_(agent_ids),
            InvestigationAssignment.is_active.is_(True),
            InvestigationAssignment.assignment_source == "manual",
            Investigation.deleted_at.is_(None),
            Investigation.status.in_(("pending", "assigned")),
            Investigation.location_confirmed_at.is_not(None),
            Investigation.latitude.is_not(None),
            Investigation.longitude.is_not(None),
        ).order_by(Investigation.id).all()
        movable_auto_assignments = _automatic_assignments_requiring_replan(
            db, region_code, set(agent_ids), work_date, include_outside_roster=bool(agent_ids),
        )
        eligible_cases_by_id = {case.id: case for case in eligible_cases}
        eligible_cases_by_id.update({case.id: case for case in manual_cases})
        eligible_cases_by_id.update({case.id: case for _assignment, case in movable_auto_assignments})
        eligible_cases = list(eligible_cases_by_id.values())
        if not eligible_cases:
            skipped_no_eligible_work += 1
            continue

        missing_case_ids = _missing_route_assigned_case_ids(db, work_date, region_code)
        if not missing_case_ids:
            skipped_no_eligible_work += 1
            continue

        history = (
            db.query(PlanningRun)
            .filter(
                PlanningRun.work_date == work_date,
                PlanningRun.region_code == region_code,
                PlanningRun.auto_publish.is_(True),
            )
            .order_by(PlanningRun.created_at.desc(), PlanningRun.id.desc())
            .all()
        )
        latest_run = history[0] if history else None

        inputs_changed = False
        if latest_run and latest_run.status in {"failed", "stale"}:
            inputs_changed = _recovery_inputs_changed(
                db,
                latest_run,
                {case.id for case in eligible_cases},
            )

        if latest_run and latest_run.status == "failed":
            permanent_unassigned = db.query(PlanningItem.id).filter(
                PlanningItem.planning_run_id == latest_run.id,
                PlanningItem.investigation_id.in_(missing_case_ids),
                PlanningItem.outcome == "unassigned",
            ).first()
            if (
                not inputs_changed
                and (
                    latest_run.error_code not in ROUTE_RECOVERY_RETRYABLE_ERRORS
                    or permanent_unassigned is not None
                )
            ):
                skipped_permanent_failure += 1
                continue

        if latest_run and latest_run.status in {"failed", "stale"}:
            attempts = 0
            if not inputs_changed:
                for prior_run in history:
                    if prior_run.status == "applied":
                        break
                    if prior_run.status in {"failed", "stale"} and _recovery_inputs_changed(
                        db,
                        prior_run,
                        {case.id for case in eligible_cases},
                    ):
                        # A different input or planner logic version starts a
                        # fresh bounded retry window; failures from the older
                        # attempt must not exhaust retries for the new one.
                        break
                    if prior_run.status == "stale":
                        attempts += 1
                    elif (
                        prior_run.status == "failed"
                        and prior_run.error_code in ROUTE_RECOVERY_RETRYABLE_ERRORS
                    ):
                        attempts += 1
                    else:
                        break

            if attempts >= ROUTE_RECOVERY_MAX_ATTEMPTS:
                skipped_retry_limit += 1
                continue

            last_attempt_at = latest_run.finished_at or latest_run.created_at
            if attempts > 0 and last_attempt_at is not None:
                delay_seconds = min(
                    ROUTE_RECOVERY_BASE_DELAY_SECONDS * (2 ** max(0, attempts - 1)),
                    1800,
                )
                elapsed = (now - _as_utc(last_attempt_at)).total_seconds()
                if elapsed < delay_seconds:
                    skipped_backoff += 1
                    continue

        assignment_ids = [
            assignment_id
            for (assignment_id,) in db.query(InvestigationAssignment.id)
            .filter(
                InvestigationAssignment.is_active.is_(True),
                InvestigationAssignment.investigation_id.in_([case.id for case in eligible_cases]),
            )
            .all()
        ]
        requester = db.get(User, latest_run.requested_by_id) if latest_run else None
        if requester is None and assignment_ids:
            first_assignment = db.get(InvestigationAssignment, assignment_ids[0])
            requester = db.get(User, first_assignment.assigned_by_id) if first_assignment else None
        if requester is None:
            requester = (
                db.query(User)
                .filter(
                    User.is_active.is_(True),
                    User.role.in_(("admin", "supervisor")),
                )
                .order_by(User.id)
                .first()
            )
        if requester is None:
            requester = db.query(User).filter(User.is_active.is_(True)).order_by(User.id).first()
        if requester is None:
            skipped_no_eligible_work += 1
            continue

        queued_run = queue_automatic_planning(
            db,
            region_code,
            requester,
            work_date,
            auto_assignment_ids=assignment_ids,
            require_missing_route=True,
        )
        if queued_run is None:
            skipped_no_eligible_work += 1
        else:
            attempted += 1

    summary = {
        "work_date": work_date.isoformat(),
        "scopes_examined": len(agent_ids_by_region),
        "scopes_queued_or_coalesced": attempted,
        "scopes_without_missing_routes": skipped_no_eligible_work,
        "scopes_in_backoff": skipped_backoff,
        "scopes_at_retry_limit": skipped_retry_limit,
        "scopes_with_permanent_failures": skipped_permanent_failure,
    }
    _log_planning_event("route_reconciliation_completed", **summary)
    return summary


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
    region_codes = {shift.region_code for shift in shifts}
    if not region_codes and investigation.region_code:
        region_codes.add(investigation.region_code)
    assignment.auto_route_work_date = work_date
    assignment.auto_route_agent_ids = impacted_ids
    assignment.auto_route_run_ids = []
    assignment.auto_route_errors = []
    assignment.auto_route_status = "queued"
    db.commit()

    run_ids: list[int] = []
    errors: list[str] = []
    assignment_regions = {
        shift.region_code for shift in shifts if shift.agent_id == assignment.agent_id
    }
    for region_code in sorted(region_codes):
        run = queue_automatic_planning(
            db,
            region_code,
            requester,
            work_date,
            auto_assignment_id=(
                assignment.id
                if not assignment_regions or region_code in assignment_regions
                else None
            ),
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
    planning_run_id: int | None = None,
    current_route_agents: dict[int, dict] | None = None,
) -> InvestigationAssignment | None:
    assignment = db.get(InvestigationAssignment, assignment_id)
    if assignment is None or (assignment.auto_route_status is None and planning_run_id is None):
        return assignment
    run_ids = list(dict.fromkeys([
        *(assignment.auto_route_run_ids or []),
        *([planning_run_id] if planning_run_id is not None else []),
    ]))
    if planning_run_id is not None:
        current_run = db.get(PlanningRun, planning_run_id)
        if current_run is not None:
            assignment.auto_route_work_date = current_run.work_date
            assignment.auto_route_run_ids = run_ids[-20:]
            assignment.auto_route_agent_ids = list(dict.fromkeys([
                *(assignment.auto_route_agent_ids or []), *(current_run.agent_ids or []), assignment.agent_id,
            ]))
    runs = db.query(PlanningRun).filter(PlanningRun.id.in_(run_ids)).all() if run_ids else []
    by_id = {run.id: run for run in runs}
    relevant_run_ids = [
        run.id for run in runs
        if assignment.investigation_id in set(run.investigation_ids or [])
    ]
    if relevant_run_ids:
        # Older failed attempts should not keep a successfully refreshed
        # assignment in a failed or partially published state.
        run_ids = [max(relevant_run_ids)]
        runs = [by_id[run_id] for run_id in run_ids if run_id in by_id]
    active_statuses = {"queued", "running", "ready"}
    has_active = any(run.status in active_statuses for run in runs)
    if has_active:
        assignment.auto_route_status = (
            "running" if any(run.status in {"running", "ready"} for run in runs) else "queued"
        )
    else:
        errors = []
        assignment_unscheduled = False
        route_failed = False
        for run_id in run_ids:
            run = by_id.get(run_id)
            if run is None:
                errors.append("planning_run_missing")
            elif assignment.investigation_id not in set(run.investigation_ids or []):
                continue
            elif run.status == "failed":
                errors.append(run.error_code or "optimization_failed")
                route_failed = True
            elif run.status == "stale" and run.error_code:
                errors.append(run.error_code)
            elif run.status == "applied":
                item = db.query(PlanningItem).filter(
                    PlanningItem.planning_run_id == run.id,
                    PlanningItem.investigation_id == assignment.investigation_id,
                ).first()
                if item is None:
                    errors.append("route_not_published")
                    route_failed = True
                elif item.outcome == "unassigned":
                    errors.append(item.reason if item and item.reason else "route_not_published")
                    assignment_unscheduled = assignment_unscheduled or bool(
                        item.investigation_id == assignment.investigation_id
                    )
                elif item.outcome != "assigned" or item.agent_id != assignment.agent_id:
                    errors.append(item.reason if item.reason else "route_not_published")
                    route_failed = True
                else:
                    route = db.query(PlanningRoute).filter(
                        PlanningRoute.planning_run_id == run.id,
                        PlanningRoute.agent_id == assignment.agent_id,
                    ).first()
                    if route is None or not _route_geometry_ready(route):
                        errors.append(
                            route.geometry_error_code if route and route.geometry_error_code
                            else "route_geometry_invalid" if route
                            else "route_not_published"
                        )
                        route_failed = True

        current_route = None
        current_route_status = None
        investigation = db.get(Investigation, assignment.investigation_id)
        if (
            assignment.is_active
            and investigation is not None
            and investigation.deleted_at is None
            and investigation.assigned_agent_id == assignment.agent_id
            and assignment.auto_route_work_date is not None
        ):
            if current_route_agents is None:
                overview = planning_route_overview(db, assignment.auto_route_work_date)
                current_route_agents = {agent["id"]: agent for agent in overview["agents"]}
            route_agent = current_route_agents.get(assignment.agent_id)
            if (
                route_agent is not None
                and route_agent["route"] is not None
                and route_agent["route"]["geometry_status"] == "ready"
                and (
                    assignment_unscheduled
                    or any(stop["investigation_id"] == assignment.investigation_id for stop in route_agent["stops"])
                )
            ):
                current_route = route_agent
            if current_route is not None:
                current_route_status = current_route["route_status"]

        errors = list(dict.fromkeys(errors))
        if assignment_unscheduled:
            assignment.auto_route_status = "unscheduled"
        elif route_failed and current_route is None:
            assignment.auto_route_status = "failed"
        elif current_route is not None:
            assignment.auto_route_status = (
                "partially_published"
                if errors or current_route_status == "partially_published"
                else "published"
            )
        else:
            assignment.auto_route_status = (
                "unscheduled"
                if assignment.is_active and (
                    assignment_unscheduled or assignment.assignment_source == "manual"
                )
                else "failed"
            )
            if not errors:
                errors.append("route_not_published" if runs else "no_routeable_assigned_work")
        assignment.auto_route_errors = errors
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
    assignment_history = db.query(InvestigationAssignment).filter(
        InvestigationAssignment.investigation_id.in_(run.investigation_ids),
    ).order_by(InvestigationAssignment.investigation_id, InvestigationAssignment.assigned_at, InvestigationAssignment.id).all() if run.investigation_ids else []
    route_events = db.query(InvestigationRouteEvent).filter(
        InvestigationRouteEvent.work_date == run.work_date,
        InvestigationRouteEvent.agent_id.in_(run.agent_ids),
        InvestigationRouteEvent.investigation_id.in_(run.investigation_ids),
        InvestigationRouteEvent.event_type == "no_contact",
    ).order_by(InvestigationRouteEvent.id).all() if run.agent_ids and run.investigation_ids else []
    return {
        # Bump this when a planner-code correction should make a prior failed
        # input eligible for one fresh automatic recovery attempt.
        "planner_logic_version": PLANNER_LOGIC_VERSION,
        "date": run.work_date.isoformat(),
        "region": run.region_code,
        "movable_investigations": sorted(run.movable_investigation_ids or []),
        "cases": [
            {
                "id": case.id,
                "status": case.status,
                "manual_assignment_required": case.manual_assignment_required,
                "reopen_on": case.reopen_on.isoformat() if case.reopen_on else None,
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
            {"id": item.id, "investigation": item.investigation_id, "agent": item.agent_id, "source": item.assignment_source, "note": item.note, "assigned_at": _iso_utc(item.assigned_at), "unassigned_at": _iso_utc(item.unassigned_at)}
            for item in sorted(active_assignments, key=lambda item: item.investigation_id)
        ],
        "assignment_history": [
            {"id": item.id, "investigation": item.investigation_id, "agent": item.agent_id, "source": item.assignment_source, "assigned_at": _iso_utc(item.assigned_at), "unassigned_at": _iso_utc(item.unassigned_at)}
            for item in assignment_history
        ],
        "route_events": [
            {"id": item.id, "investigation": item.investigation_id, "agent": item.agent_id, "state": item.state, "retry_number": item.retry_number, "reason": item.reason, "attempted_at": _iso_utc(item.attempted_at), "contact_from": _iso_utc(item.contact_available_from), "contact_until": _iso_utc(item.contact_available_until)}
            for item in route_events
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
                "source": shift.source,
                "schedule_version_id": shift.schedule_version_id,
                "break": [_iso_utc(shift.break_starts_at), _iso_utc(shift.break_ends_at)],
                "last_completed": [shift.last_completed_investigation_id, shift.last_completed_report_id, _iso_utc(shift.last_completed_at), shift.last_completed_latitude, shift.last_completed_longitude],
                "last_attempted": [shift.last_attempted_investigation_id, _iso_utc(shift.last_attempted_at), shift.last_attempted_latitude, shift.last_attempted_longitude],
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


def _priority_rank(priority: str | None) -> int:
    return {"urgent": 0, "high": 1, "normal": 2}.get(priority or "normal", 2)


def _original_assignment_order(case: Investigation) -> tuple[datetime, int]:
    assignments = getattr(case, "assignments", None) or []
    created_at = getattr(case, "created_at", None)
    assigned_at = min(
        (_as_utc(item.assigned_at) for item in assignments if item.assigned_at is not None),
        default=(
            _as_utc(created_at)
            if created_at is not None
            else datetime.max.replace(tzinfo=timezone.utc)
        ),
    )
    return assigned_at, case.id


def _priority_inversions(job_ids: list[int], case_by_id: dict[int, Investigation]) -> list[tuple[int, int]]:
    """Return lower-priority stops that appear before higher-priority stops."""
    inversions = []
    for earlier_index, earlier_id in enumerate(job_ids):
        earlier = case_by_id.get(earlier_id)
        if earlier is None:
            continue
        for later_id in job_ids[earlier_index + 1:]:
            later = case_by_id.get(later_id)
            if (
                later is not None
                and getattr(earlier, "_route_retry_pending", False) == getattr(later, "_route_retry_pending", False)
                and _priority_rank(earlier.priority) > _priority_rank(later.priority)
            ):
                inversions.append((earlier_id, later_id))
    return inversions


def _assignment_time_inversions(job_ids: list[int], case_by_id: dict[int, Investigation]) -> list[tuple[int, int]]:
    """Return same-priority stops that violate first-assigned-first-served."""
    inversions = []
    for earlier_index, earlier_id in enumerate(job_ids):
        earlier = case_by_id.get(earlier_id)
        if earlier is None:
            continue
        for later_id in job_ids[earlier_index + 1:]:
            later = case_by_id.get(later_id)
            if (
                later is not None
                and getattr(earlier, "_route_retry_pending", False) == getattr(later, "_route_retry_pending", False)
                and _priority_rank(earlier.priority) == _priority_rank(later.priority)
                and _original_assignment_order(earlier) > _original_assignment_order(later)
            ):
                inversions.append((earlier_id, later_id))
    return inversions


def _retry_phase_inversions(job_ids: list[int], case_by_id: dict[int, Investigation]) -> list[tuple[int, int]]:
    inversions = []
    for earlier_index, earlier_id in enumerate(job_ids):
        earlier = case_by_id.get(earlier_id)
        if earlier is None or not getattr(earlier, "_route_retry_pending", False):
            continue
        for later_id in job_ids[earlier_index + 1:]:
            later = case_by_id.get(later_id)
            if later is not None and not getattr(later, "_route_retry_pending", False):
                inversions.append((earlier_id, later_id))
    return inversions


def _route_order_inversions(job_ids: list[int], case_by_id: dict[int, Investigation]) -> list[tuple[int, int]]:
    return (
        _retry_phase_inversions(job_ids, case_by_id)
        + _priority_inversions(job_ids, case_by_id)
        + _assignment_time_inversions(job_ids, case_by_id)
    )


def _priority_route_score(route: dict, case_by_id: dict[int, Investigation]) -> tuple:
    """Rank feasible route candidates by priority order, early service, then travel."""
    job_steps = [
        step for step in route.get("steps", [])
        if isinstance(step, dict) and step.get("type") == "job"
    ]
    job_ids = [step.get("id") for step in job_steps]
    inversions = _priority_inversions(job_ids, case_by_id)
    assignment_inversions = _assignment_time_inversions(job_ids, case_by_id)
    retry_phase_inversions = _retry_phase_inversions(job_ids, case_by_id)
    urgent_inversions = sum(
        1 for earlier_id, later_id in inversions
        if _priority_rank(case_by_id[earlier_id].priority) > 0
        and _priority_rank(case_by_id[later_id].priority) == 0
    )
    high_inversions = sum(
        1 for earlier_id, later_id in inversions
        if _priority_rank(case_by_id[earlier_id].priority) == 2
        and _priority_rank(case_by_id[later_id].priority) == 1
    )
    priority_service_starts = {"urgent": [], "high": [], "normal": []}
    for step in job_steps:
        case = case_by_id.get(step.get("id"))
        arrival = step.get("arrival")
        waiting = step.get("waiting_time", 0)
        if (
            case is None
            or isinstance(arrival, bool)
            or not isinstance(arrival, (int, float))
            or isinstance(waiting, bool)
            or not isinstance(waiting, (int, float))
        ):
            continue
        priority_service_starts[case.priority if case.priority in priority_service_starts else "normal"].append(
            arrival + waiting,
        )
    service_score = tuple(
        sum(priority_service_starts[priority])
        for priority in ("urgent", "high", "normal")
    )
    duration = route.get("duration")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)):
        duration = float("inf")
    return len(retry_phase_inversions), urgent_inversions, high_inversions, len(assignment_inversions), *service_score, duration


def _priority_route_payload(
    vehicle: dict,
    route_job_ids: list[int],
    jobs_by_id: dict[int, dict],
    case_by_id: dict[int, Investigation],
    point_indexes: dict[tuple[float, float], int],
    local_index: dict[int, int],
    durations: list[list[int]],
    distances: list[list[int]],
    origin: tuple[float, float],
    destination: tuple[float, float] | None,
) -> dict:
    """Build a VROOM re-sequencing problem with lexicographic priority penalties."""
    baseline_position = {case_id: index for index, case_id in enumerate(route_job_ids)}
    ordered_ids = sorted(
        route_job_ids,
        key=lambda case_id: (
            bool(getattr(case_by_id[case_id], "_route_retry_pending", False)),
            _priority_rank(case_by_id[case_id].priority),
            *_original_assignment_order(case_by_id[case_id]),
            baseline_position[case_id],
        ),
    )
    case_local_indexes = [
        local_index[point_indexes[(round(case_by_id[case_id].latitude, 6), round(case_by_id[case_id].longitude, 6))]]
        for case_id in route_job_ids
    ]
    origin_local_index = local_index[point_indexes[(round(origin[0], 6), round(origin[1], 6))]]
    matrix_indexes = [origin_local_index, *case_local_indexes]
    if destination is not None:
        matrix_indexes.append(local_index[point_indexes[(round(destination[0], 6), round(destination[1], 6))]])

    expanded_durations = [[durations[source][target] for target in matrix_indexes] for source in matrix_indexes]
    expanded_distances = [[distances[source][target] for target in matrix_indexes] for source in matrix_indexes]
    job_count = len(route_job_ids)
    max_arc = max((value for row in expanded_durations for value in row), default=0)
    travel_bound = max(1, (job_count + 1) * max_arc)
    assignment_penalty = travel_bound + 1
    high_penalty = (job_count + 1) * assignment_penalty + travel_bound + 1
    urgent_penalty = (job_count + 1) * high_penalty + travel_bound + 1
    retry_phase_penalty = (job_count + 1) * urgent_penalty + travel_bound + 1
    costs = [row[:] for row in expanded_durations]
    for source_position, source_case_id in enumerate(route_job_ids, start=1):
        source_rank = _priority_rank(case_by_id[source_case_id].priority)
        for target_position, target_case_id in enumerate(route_job_ids, start=1):
            if source_position == target_position:
                continue
            target_rank = _priority_rank(case_by_id[target_case_id].priority)
            source_retry = bool(getattr(case_by_id[source_case_id], "_route_retry_pending", False))
            target_retry = bool(getattr(case_by_id[target_case_id], "_route_retry_pending", False))
            if source_retry and not target_retry:
                costs[source_position][target_position] += retry_phase_penalty
            elif source_retry == target_retry and source_rank > target_rank:
                costs[source_position][target_position] += urgent_penalty if target_rank == 0 else high_penalty
            elif (
                source_retry == target_retry
                and source_rank == target_rank
                and _original_assignment_order(case_by_id[source_case_id])
                > _original_assignment_order(case_by_id[target_case_id])
            ):
                costs[source_position][target_position] += assignment_penalty

    priority_vehicle = dict(vehicle)
    priority_vehicle["start_index"] = 0
    priority_vehicle["steps"] = [{"type": "job", "id": case_id} for case_id in ordered_ids]
    if destination is not None:
        priority_vehicle["end_index"] = job_count + 1
    else:
        priority_vehicle.pop("end", None)
        priority_vehicle.pop("end_index", None)

    priority_jobs = []
    for position, case_id in enumerate(route_job_ids, start=1):
        job = dict(jobs_by_id[case_id])
        job["location_index"] = position
        priority_jobs.append(job)
    return {
        "vehicles": [priority_vehicle],
        "jobs": priority_jobs,
        "matrices": {
            "car": {
                "durations": expanded_durations,
                "distances": expanded_distances,
                "costs": costs,
            },
        },
    }


def _priority_route_from_solution(solution: dict, agent_id: int, expected_job_ids: set[int]) -> dict | None:
    routes = solution.get("routes")
    if not isinstance(routes, list) or len(routes) != 1 or not isinstance(routes[0], dict):
        return None
    route = routes[0]
    if route.get("vehicle") != agent_id or solution.get("unassigned"):
        return None
    steps = route.get("steps")
    if not isinstance(steps, list):
        return None
    found_job_ids = []
    for step in steps:
        if not isinstance(step, dict) or step.get("type") != "job":
            continue
        case_id = step.get("id")
        if isinstance(case_id, bool) or not isinstance(case_id, int):
            return None
        found_job_ids.append(case_id)
    if len(found_job_ids) != len(expected_job_ids) or set(found_job_ids) != expected_job_ids:
        return None
    return route


def _region_skill(region_code: str) -> int:
    codes = sorted(catalog()["region_codes"])
    if region_code not in codes:
        raise PlanningConflict("invalid_region")
    return 10_000 + codes.index(region_code)


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
    now: datetime | None = None,
    radius_eligible_agent_ids_by_case: dict[int, set[int]] | None = None,
    manual_locked_case_ids: set[int] | None = None,
) -> list[dict]:
    # Keep optimizer input and schedule validation on the same clock snapshot.
    # VROOM commonly starts at the exact lower bound sent in the vehicle
    # time window; comparing it with a later wall-clock reading can reject an
    # otherwise valid same-day route while the optimizer is running.
    planning_now = _as_utc(now or datetime.now(timezone.utc))
    local_index = {global_index: index for index, global_index in enumerate(component)}
    component_set = set(component)
    component_durations = [[int(durations[source][target]) for target in component] for source in component]
    component_distances = [[int(distances[source][target]) for target in component] for source in component]
    jobs = []
    case_by_id = {case.id: case for case in cases}
    case_radius_skill = {
        case.id: 10_000_000 + index
        for index, case in enumerate(sorted(cases, key=lambda item: item.id), start=1)
    }
    radius_eligible_agent_ids_by_case = radius_eligible_agent_ids_by_case or {}
    manual_locked_case_ids = manual_locked_case_ids or set()
    for case in cases:
        coordinate = (round(case.latitude, 6), round(case.longitude, 6))
        index = point_indexes[coordinate]
        if index not in component_set:
            continue
        is_manual_override = case.id in manual_locked_case_ids and locked.get(case.id) == case.assigned_agent_id
        job = {
            "id": case.id,
            "location": [case.longitude, case.latitude],
            "location_index": local_index[index],
            "service": case.service_duration_seconds,
            "priority": 1 if getattr(case, "_route_retry_pending", False) else PRIORITY_VALUES.get(case.priority, 10),
            "skills": [] if is_manual_override else [
                _region_skill(case.region_code),
                case_radius_skill[case.id],
            ],
        }
        windows = []
        contact_from = getattr(case, "_route_contact_available_from", None)
        contact_until = getattr(case, "_route_contact_available_until", None)
        if case.visit_not_before_at or case.visit_due_at or contact_from or contact_until:
            earliest_start_candidates = [
                value for value in (case.visit_not_before_at, contact_from) if value is not None
            ]
            earliest_start = max((_epoch_ceil(value) for value in earliest_start_candidates), default=None)
            latest_end_candidates = [
                value for value in (case.visit_due_at, contact_until) if value is not None
            ]
            latest_end = min((_epoch(value) for value in latest_end_candidates), default=None)
            latest_start = latest_end - case.service_duration_seconds if latest_end is not None else None
            windows.append([
                earliest_start if earliest_start is not None else min(_epoch(_planning_floor(s, planning_now)) for s in shifts),
                int(latest_start) if latest_start is not None else max(_epoch(s.shift_ends_at) for s in shifts),
            ])
            job["time_windows"] = windows
        locked_agent = locked.get(case.id)
        if locked_agent:
            job["skills"].append(1_000_000 + locked_agent)
        jobs.append(job)

    vehicles = []
    vehicle_by_agent: dict[int, dict] = {}
    shift_by_agent = {shift.agent_id: shift for shift in shifts}
    break_required_by_agent: dict[int, bool] = {}
    earliest_route_departure_epoch_by_agent: dict[int, int] = {}
    for shift in shifts:
        origin_latitude, origin_longitude, _origin_label = _route_origin(shift, planning_now)
        start = (round(origin_latitude, 6), round(origin_longitude, 6))
        start_global = point_indexes[start]
        destination = _route_destination(shift)
        end_global = None
        if destination is not None:
            end_lat, end_lon, _end_label = destination
            end_global = point_indexes[(round(end_lat, 6), round(end_lon, 6))]
        if start_global not in component_set or (end_global is not None and end_global not in component_set):
            continue
        remaining_open = max(0, shift.max_open_cases - open_case_counts.get(shift.agent_id, 0))
        assigned_selected_count = sum(
            1 for case in cases if case.assigned_agent_id == shift.agent_id
        )
        task_cap = min(shift.max_visits, remaining_open + assigned_selected_count)
        if task_cap < 1:
            continue
        floor = _planning_floor(shift, planning_now)
        end_epoch = _epoch(shift.shift_ends_at)
        if _epoch(floor) >= end_epoch:
            continue
        vehicle_skills = [_region_skill(code) for code in sorted(catalog()["region_codes"])] if shift.region_code == ALL_REGIONS else [_region_skill(shift.region_code)]
        vehicle_skills.append(1_000_000 + shift.agent_id)
        vehicle_skills.extend(
            case_radius_skill[case.id]
            for case in cases
            if case.id not in manual_locked_case_ids
            and shift.agent_id in radius_eligible_agent_ids_by_case.get(case.id, set())
        )
        vehicle = {
            "id": shift.agent_id,
            "profile": "car",
            "start": [start[1], start[0]],
            "start_index": local_index[start_global],
            "time_window": [_epoch(floor), end_epoch],
            "max_tasks": max(1, task_cap),
            "skills": vehicle_skills,
        }
        if destination is not None and end_global is not None:
            vehicle["end"] = [round(destination[1], 6), round(destination[0], 6)]
            vehicle["end_index"] = local_index[end_global]
        needs_break = bool(shift.break_starts_at and shift.break_ends_at and _epoch(shift.break_ends_at) > _epoch(floor))
        if needs_break and shift.break_starts_at and shift.break_ends_at:
            break_start = _epoch(shift.break_starts_at)
            break_end = _epoch(shift.break_ends_at)
            if break_start < _epoch(floor):
                floor = _as_utc(shift.break_ends_at)
                vehicle["time_window"] = [_epoch(floor), end_epoch]
                needs_break = False
            else:
                vehicle["breaks"] = [{
                    "id": 2_000_000 + shift.agent_id,
                    "time_windows": [[break_start, break_start]],
                    "service": break_end - break_start,
                }]
        earliest_route_departure_epoch_by_agent[shift.agent_id] = _epoch(floor)
        break_required_by_agent[shift.agent_id] = needs_break
        vehicles.append(vehicle)
        vehicle_by_agent[shift.agent_id] = vehicle

    if not jobs or not vehicles:
        return []
    payload = {
        "vehicles": vehicles,
        "jobs": jobs,
        "matrices": {"car": {"durations": component_durations, "distances": component_distances}},
    }
    solution = solver.solve(payload)
    priority_warning_by_agent: dict[int, list[dict]] = {}
    jobs_by_id = {job["id"]: job for job in jobs}
    prioritized_routes = []
    for baseline_route in solution.get("routes", []):
        if not isinstance(baseline_route, dict):
            prioritized_routes.append(baseline_route)
            continue
        agent_id = baseline_route.get("vehicle")
        steps = baseline_route.get("steps")
        if (
            isinstance(agent_id, bool)
            or not isinstance(agent_id, int)
            or not isinstance(steps, list)
            or agent_id not in vehicle_by_agent
        ):
            prioritized_routes.append(baseline_route)
            continue
        route_job_ids = [
            step["id"]
            for step in steps
            if isinstance(step, dict) and step.get("type") == "job" and isinstance(step.get("id"), int)
        ]
        if any(case_id not in jobs_by_id or case_id not in case_by_id for case_id in route_job_ids):
            prioritized_routes.append(baseline_route)
            continue
        if not _route_order_inversions(route_job_ids, case_by_id):
            prioritized_routes.append(baseline_route)
            continue

        shift = shift_by_agent[agent_id]
        origin_latitude, origin_longitude, _origin_label = _route_origin(shift, planning_now)
        destination = _route_destination(shift)
        destination_point = (destination[0], destination[1]) if destination is not None else None
        priority_payload = _priority_route_payload(
            vehicle_by_agent[agent_id],
            route_job_ids,
            jobs_by_id,
            case_by_id,
            point_indexes,
            local_index,
            component_durations,
            component_distances,
            (origin_latitude, origin_longitude),
            destination_point,
        )
        expected_route_ids = set(route_job_ids)
        best_route = baseline_route
        best_route_score = _priority_route_score(best_route, case_by_id)
        search_limit_reached = False
        priority_order_infeasible = False
        priority_payload["options"] = {"l": PRIORITY_SEARCH_LIMIT_SECONDS}
        candidate_solution = None
        priority_search_started = monotonic()
        try:
            candidate_solution = solver.solve(priority_payload)
            candidate_route = _priority_route_from_solution(candidate_solution, agent_id, expected_route_ids)
        except RoutingUnavailable as error:
            candidate_route = None
            priority_order_infeasible = error.args[0] == "vroom_solver_failed"
        search_limit_reached = (
            monotonic() - priority_search_started >= PRIORITY_SEARCH_LIMIT_SECONDS * 0.8
        )

        if candidate_route is not None:
            candidate_route_score = _priority_route_score(candidate_route, case_by_id)
            if candidate_route_score < best_route_score:
                best_route = candidate_route
                best_route_score = candidate_route_score

        best_job_ids = [
            step["id"] for step in best_route["steps"]
            if isinstance(step, dict) and step.get("type") == "job"
        ]

        if _route_order_inversions(best_job_ids, case_by_id):
            # If urgent/high/normal cannot be followed, continue from VROOM's
            # original feasible route so the optimizer searches nearby orders
            # while preserving hard schedule constraints.
            unseeded_payload = {
                **priority_payload,
                "vehicles": [
                    {
                        **priority_payload["vehicles"][0],
                        "steps": [
                            {"type": "job", "id": case_id}
                            for case_id in route_job_ids
                        ],
                    }
                ],
            }
            priority_search_started = monotonic()
            try:
                candidate_solution = solver.solve(unseeded_payload)
                candidate_route = _priority_route_from_solution(candidate_solution, agent_id, expected_route_ids)
            except RoutingUnavailable as error:
                candidate_route = None
                if error.args[0] == "vroom_solver_failed":
                    priority_order_infeasible = True
            search_limit_reached = search_limit_reached or (
                monotonic() - priority_search_started >= PRIORITY_SEARCH_LIMIT_SECONDS * 0.8
            )
            if candidate_route is not None:
                candidate_route_score = _priority_route_score(candidate_route, case_by_id)
                if candidate_route_score < best_route_score:
                    best_route = candidate_route
                    best_route_score = candidate_route_score

        chosen_ids = [
            step["id"] for step in best_route["steps"]
            if isinstance(step, dict) and step.get("type") == "job"
        ]
        remaining_inversions = _priority_inversions(chosen_ids, case_by_id)
        remaining_retry_phase_inversions = _retry_phase_inversions(chosen_ids, case_by_id)
        remaining_assignment_inversions = _assignment_time_inversions(chosen_ids, case_by_id)
        if search_limit_reached or (remaining_inversions and not priority_order_infeasible):
            priority_warning_by_agent[agent_id] = [{
                "type": "priority_order",
                "agent_id": agent_id,
                "investigation_id": None,
                "reference_number": None,
                "deferred_investigation_id": None,
                "deferred_reference_number": None,
                "reason": "search_limit",
            }]
        elif remaining_inversions:
            priority_warning_by_agent[agent_id] = [
                {
                    "type": "priority_order",
                    "agent_id": agent_id,
                    "investigation_id": earlier_id,
                    "reference_number": getattr(case_by_id[earlier_id], "reference_number", str(earlier_id)),
                    "deferred_investigation_id": later_id,
                    "deferred_reference_number": getattr(case_by_id[later_id], "reference_number", str(later_id)),
                    "reason": "schedule_constraint",
                }
                for earlier_id, later_id in remaining_inversions
            ]
        elif remaining_retry_phase_inversions:
            priority_warning_by_agent[agent_id] = [
                {
                    "type": "priority_order",
                    "agent_id": agent_id,
                    "investigation_id": earlier_id,
                    "reference_number": getattr(case_by_id[earlier_id], "reference_number", str(earlier_id)),
                    "deferred_investigation_id": later_id,
                    "deferred_reference_number": getattr(case_by_id[later_id], "reference_number", str(later_id)),
                    "reason": "schedule_constraint",
                }
                for earlier_id, later_id in remaining_retry_phase_inversions
            ]
        elif remaining_assignment_inversions:
            priority_warning_by_agent[agent_id] = [
                {
                    "type": "priority_order",
                    "agent_id": agent_id,
                    "investigation_id": earlier_id,
                    "reference_number": getattr(case_by_id[earlier_id], "reference_number", str(earlier_id)),
                    "deferred_investigation_id": later_id,
                    "deferred_reference_number": getattr(case_by_id[later_id], "reference_number", str(later_id)),
                    "reason": "assignment_time_constraint",
                }
                for earlier_id, later_id in remaining_assignment_inversions
            ]
        prioritized_routes.append(best_route)
    solution["routes"] = prioritized_routes
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
        duration_values = [step.get("duration") for step in steps]
        has_cumulative_durations = any(value is not None for value in duration_values)
        if has_cumulative_durations and any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            or value < 0
            for value in duration_values
        ):
            raise RoutingUnavailable("vroom_solution_duration_invalid")
        shift = shift_by_agent[agent_id]
        origin_latitude, origin_longitude, _origin_label = _route_origin(shift, planning_now)
        previous_index = point_indexes[(round(origin_latitude, 6), round(origin_longitude, 6))]
        start_arrival = steps[0].get("arrival")
        if isinstance(start_arrival, bool) or not isinstance(start_arrival, (int, float)) or not isfinite(start_arrival):
            raise RoutingUnavailable("vroom_solution_arrival_invalid")
        previous_arrival = int(start_arrival)
        floor_epoch = _epoch(_planning_floor(shift, planning_now))
        shift_end_epoch = _epoch(shift.shift_ends_at)
        if previous_arrival < floor_epoch:
            _reject_vroom_schedule("start_before_planning_floor", floor_epoch - previous_arrival)
        if previous_arrival > shift_end_epoch:
            _reject_vroom_schedule("start_after_shift_end", previous_arrival - shift_end_epoch)
        start_waiting = steps[0].get("waiting_time")
        if isinstance(start_waiting, bool) or not isinstance(start_waiting, (int, float)) or not isfinite(start_waiting) or start_waiting < 0:
            raise RoutingUnavailable("vroom_solution_waiting_invalid")
        previous_departure = previous_arrival + int(start_waiting)
        planned_departure_at = datetime.fromtimestamp(previous_departure, timezone.utc)
        estimate_departure_epoch = earliest_route_departure_epoch_by_agent.get(agent_id, floor_epoch)
        cumulative_waiting_seconds = int(start_waiting)
        cumulative_service_seconds = 0
        previous_job_travel_seconds = int(steps[0].get("duration", 0)) if has_cumulative_durations else 0
        sequence = 0
        break_seen = False
        break_duration = 0
        pending_break: dict[str, int] | None = None
        for step in steps[1:-1]:
            if not isinstance(step, dict) or not isinstance(step.get("type"), str):
                raise RoutingUnavailable("vroom_solution_shape_invalid")
            if step.get("type") == "break":
                if break_seen or not shift.break_starts_at or not shift.break_ends_at:
                    raise RoutingUnavailable("vroom_solution_break_invalid")
                arrival_value = step.get("arrival")
                waiting_value = step.get("waiting_time")
                if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) for value in (arrival_value, waiting_value)) or waiting_value < 0:
                    raise RoutingUnavailable("vroom_solution_break_invalid")
                break_arrival = int(arrival_value)
                break_start = break_arrival + int(waiting_value)
                expected_start = _epoch(shift.break_starts_at)
                expected_end = _epoch(shift.break_ends_at)
                service = step.get("service", expected_end - expected_start)
                if isinstance(service, bool) or not isinstance(service, (int, float)) or int(service) != expected_end - expected_start:
                    raise RoutingUnavailable("vroom_solution_break_invalid")
                if break_arrival < previous_departure or break_start != expected_start or break_start + int(service) != expected_end:
                    raise RoutingUnavailable("vroom_solution_break_invalid")
                if has_cumulative_durations:
                    reported_travel = int(step["duration"])
                    elapsed = break_arrival - previous_arrival
                    minimum_elapsed = reported_travel + cumulative_service_seconds + cumulative_waiting_seconds
                    if reported_travel < previous_job_travel_seconds:
                        _reject_vroom_schedule("break_travel_duration_decreased", previous_job_travel_seconds - reported_travel)
                    if elapsed < minimum_elapsed:
                        _reject_vroom_schedule("break_arrival_before_cumulative_work", minimum_elapsed - elapsed)
                    travel_before_break = reported_travel - previous_job_travel_seconds
                else:
                    travel_before_break = break_arrival - previous_departure
                cumulative_waiting_seconds += int(waiting_value)
                cumulative_service_seconds += int(service)
                previous_departure = expected_end
                pending_break = {
                    "start": expected_start,
                    "duration": int(service),
                    "travel_before": max(0, int(travel_before_break)),
                }
                break_seen = True
                break_duration = int(service)
                continue
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
            waiting = step.get("waiting_time")
            if isinstance(waiting, bool) or not isinstance(waiting, (int, float)) or not isfinite(waiting) or waiting < 0:
                raise RoutingUnavailable("vroom_solution_waiting_invalid")
            waiting = int(waiting)
            service_start = arrival + waiting
            coordinate = (round(case.latitude, 6), round(case.longitude, 6))
            current_index = point_indexes[coordinate]
            travel_seconds = int(durations[previous_index][current_index])
            if pending_break is None:
                earliest_arrival_epoch = estimate_departure_epoch + travel_seconds
            else:
                travel_before_break = min(
                    travel_seconds,
                    pending_break["travel_before"],
                )
                travel_after_break = travel_seconds - travel_before_break
                earliest_break_arrival_epoch = estimate_departure_epoch + travel_before_break
                earliest_arrival_epoch = (
                    max(earliest_break_arrival_epoch, pending_break["start"])
                    + pending_break["duration"]
                    + travel_after_break
                )
                pending_break = None
            if service_start < earliest_arrival_epoch:
                _reject_vroom_schedule(
                    "job_service_before_physical_arrival",
                    earliest_arrival_epoch - service_start,
                )
            if has_cumulative_durations:
                reported_travel = int(step["duration"])
                expected_travel = previous_job_travel_seconds + travel_seconds
                if reported_travel < expected_travel:
                    _reject_vroom_schedule("job_travel_duration_short", expected_travel - reported_travel)
                elapsed = arrival - previous_arrival
                minimum_elapsed = reported_travel + cumulative_service_seconds + cumulative_waiting_seconds
                if elapsed < minimum_elapsed:
                    _reject_vroom_schedule("job_arrival_before_cumulative_work", minimum_elapsed - elapsed)
            else:
                earliest = previous_departure + travel_seconds
                if arrival < earliest:
                    _reject_vroom_schedule("job_arrival_before_travel", earliest - arrival)
                if service_start < earliest:
                    _reject_vroom_schedule("job_service_before_travel", earliest - service_start)
            if service_start + case.service_duration_seconds > shift_end_epoch:
                _reject_vroom_schedule(
                    "job_service_after_shift_end",
                    service_start + case.service_duration_seconds - shift_end_epoch,
                )
            if case.visit_not_before_at and service_start < _epoch_ceil(case.visit_not_before_at):
                _reject_vroom_schedule("job_service_before_visit_window", _epoch_ceil(case.visit_not_before_at) - service_start)
            if case.visit_due_at and service_start + case.service_duration_seconds > _epoch(case.visit_due_at):
                _reject_vroom_schedule(
                    "job_service_after_visit_window",
                    service_start + case.service_duration_seconds - _epoch(case.visit_due_at),
                )
            if case.id in locked and locked[case.id] != agent_id:
                raise RoutingUnavailable("vroom_solution_locked_assignment_invalid")
            sequence += 1
            outcomes.append({
                "investigation_id": case.id,
                "agent_id": agent_id,
                "outcome": "assigned",
                "reason": None,
                "sequence": sequence,
                "estimated_arrival_at": datetime.fromtimestamp(earliest_arrival_epoch, timezone.utc),
                "planned_arrival_at": datetime.fromtimestamp(arrival, timezone.utc),
                "planned_departure_at": planned_departure_at,
                "estimated_service_start_at": datetime.fromtimestamp(service_start, timezone.utc),
                "waiting_seconds": waiting,
                "service_seconds": case.service_duration_seconds,
                "route_break_seconds": 0,
                "travel_seconds": travel_seconds,
                "travel_metres": int(distances[previous_index][current_index]),
            })
            reported_ids.add(case.id)
            cumulative_waiting_seconds += waiting
            cumulative_service_seconds += case.service_duration_seconds
            if has_cumulative_durations:
                previous_job_travel_seconds = int(step["duration"])
            previous_index = current_index
            previous_departure = service_start + case.service_duration_seconds
            estimate_departure_epoch = service_start + case.service_duration_seconds
        if break_required_by_agent.get(agent_id, False) and not break_seen:
            raise RoutingUnavailable("vroom_solution_break_missing")
        if break_duration and sequence:
            next(item for item in outcomes if item.get("agent_id") == agent_id and item.get("sequence") == 1)["route_break_seconds"] = break_duration
        if priority_warning_by_agent.get(agent_id) and sequence:
            first_outcome = next(
                item for item in outcomes
                if item.get("agent_id") == agent_id and item.get("sequence") == 1
            )
            first_outcome["_priority_order_warnings"] = priority_warning_by_agent[agent_id]
        end_arrival = steps[-1].get("arrival")
        if isinstance(end_arrival, bool) or not isinstance(end_arrival, (int, float)) or not isfinite(end_arrival):
            raise RoutingUnavailable("vroom_solution_arrival_invalid")
        destination = _route_destination(shift)
        if destination is not None:
            end_latitude, end_longitude, _end_label = destination
            end_coordinate = (round(end_latitude, 6), round(end_longitude, 6))
            end_index = point_indexes[end_coordinate]
        else:
            end_index = previous_index
        if has_cumulative_durations:
            end_travel = int(steps[-1]["duration"])
            expected_travel = previous_job_travel_seconds + int(durations[previous_index][end_index])
            if end_travel < expected_travel:
                _reject_vroom_schedule("end_travel_duration_short", expected_travel - end_travel)
            elapsed = int(end_arrival) - previous_arrival
            minimum_elapsed = end_travel + cumulative_service_seconds + cumulative_waiting_seconds
            if elapsed < minimum_elapsed:
                _reject_vroom_schedule("end_arrival_before_cumulative_work", minimum_elapsed - elapsed)
        else:
            end_earliest = previous_departure + int(durations[previous_index][end_index])
            if int(end_arrival) < end_earliest:
                _reject_vroom_schedule("end_before_final_stop_complete", end_earliest - int(end_arrival))
        if int(end_arrival) > shift_end_epoch:
            _reject_vroom_schedule("end_after_shift_end", int(end_arrival) - shift_end_epoch)
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
            planned_arrival_at=proposal.get("planned_arrival_at"),
            estimated_service_start_at=proposal.get("estimated_service_start_at"),
            waiting_seconds=proposal.get("waiting_seconds"),
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
             item.planned_arrival_at.isoformat() if item.planned_arrival_at else None,
             item.estimated_service_start_at.isoformat() if item.estimated_service_start_at else None,
             item.waiting_seconds, item.travel_seconds, item.travel_metres]
            for item in items
        ],
        "planned_departures": [
            [
                route["agent_id"],
                route["planned_departure_at"].isoformat()
                if route.get("planned_departure_at") else None,
            ]
            for route in route_geometries or []
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
        road_snap_warning_count=sum(
            1 for warning in (run.warnings or [])
            if warning.get("type") == "road_snap_distance"
        ),
        blocked_assignment_warning_count=sum(
            1 for warning in (run.warnings or [])
            if warning.get("type") == "blocked_assigned_investigation"
        ),
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
    assignment_warnings = [
        warning for warning in (run.warnings or [])
        if warning.get("type") == "blocked_assigned_investigation"
    ]
    run.warnings = assignment_warnings
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
        deferred_events = db.query(InvestigationRouteEvent).filter(
            InvestigationRouteEvent.work_date == run.work_date,
            InvestigationRouteEvent.agent_id.in_(run.agent_ids),
            InvestigationRouteEvent.investigation_id.in_(run.investigation_ids),
            InvestigationRouteEvent.event_type == "no_contact",
            InvestigationRouteEvent.parent_event_id.is_(None),
            InvestigationRouteEvent.retry_number == 0,
            InvestigationRouteEvent.state == "deferred",
        ).order_by(InvestigationRouteEvent.attempted_at.desc(), InvestigationRouteEvent.id.desc()).all() if run.agent_ids and run.investigation_ids else []
        deferred_by_case = {}
        for event in deferred_events:
            deferred_by_case.setdefault(event.investigation_id, event)
        for case in case_rows:
            event = deferred_by_case.get(case.id)
            if event is not None and event.agent_id == case.assigned_agent_id:
                case._route_retry_pending = True
                case._route_contact_available_from = event.contact_available_from
                case._route_contact_available_until = event.contact_available_until
            else:
                case._route_retry_pending = False
                case._route_contact_available_from = None
                case._route_contact_available_until = None
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
        manual_owners = {
            item.investigation_id: item.agent_id
            for item in active_assignments
            if item.assignment_source == "manual"
        }
        automatic_owners = {
            item.investigation_id: item.agent_id
            for item in active_assignments
            if item.assignment_source == "automatic"
        }
        movable_ids = set(run.movable_investigation_ids or [])
        current_now = _database_now(db)
        in_progress_agent_ids = set(
            agent_id for (agent_id,) in db.query(Investigation.assigned_agent_id).filter(
                Investigation.assigned_agent_id.in_(run.agent_ids),
                Investigation.deleted_at.is_(None),
                Investigation.status == "in_progress",
            ).distinct().all() if agent_id is not None
        ) if run.agent_ids else set()

        preflight: dict[int, tuple[str, str | None]] = {}
        eligible_agents: list[AgentShift] = []
        agent_blockers: dict[int, str] = {}
        for agent_id in run.agent_ids:
            agent = agent_by_id.get(agent_id)
            shift = shift_by_agent.get(agent_id)
            region_match = bool(shift and (run.region_code == ALL_REGIONS or shift.region_code in {run.region_code, ALL_REGIONS}))
            if not agent or agent.role != "agent" or not agent.is_active:
                agent_blockers[agent_id] = "agent_not_eligible"
                continue
            if shift is None or not shift.is_available:
                agent_blockers[agent_id] = "agent_shift_unavailable"
                continue
            if not region_match:
                agent_blockers[agent_id] = "agent_region_mismatch"
                continue
            if shift.start_latitude is None or shift.start_longitude is None:
                agent_blockers[agent_id] = "no_routable_agent_start"
                continue

            floor = _planning_floor(shift, current_now)
            if floor >= _as_utc(shift.shift_ends_at):
                agent_blockers[agent_id] = "shift_ended"
                continue
            if agent_id in in_progress_agent_ids:
                # Keep the in-progress visit and its existing route intact.
                # Once a visit report records its completion, the trigger
                # replans from that confirmed stop.
                agent_blockers[agent_id] = "agent_in_progress"
                continue
            eligible_agents.append(shift)

        if not eligible_agents:
            for case in case_rows:
                if case.deleted_at is None and case.status in {"pending", "assigned"} and case.location_confirmed:
                    if case.id in movable_ids:
                        owner_id = automatic_owners.get(case.id)
                        owner_shift = (
                            shift_by_agent.get(owner_id)
                            or db.query(AgentShift).filter(
                                AgentShift.agent_id == owner_id,
                                AgentShift.work_date == run.work_date,
                            ).first()
                        ) if owner_id is not None else None
                        reason = (
                            "outside_service_radius"
                            if owner_shift and not _case_within_service_radius(case, owner_shift)
                            else "waiting_for_reassignment"
                        )
                    else:
                        fixed_agent = locked.get(case.id) or case.assigned_agent_id
                        reason = agent_blockers.get(fixed_agent) if fixed_agent is not None else None
                        if reason is None and run.agent_ids and all(
                            agent_blockers.get(agent_id) == "agent_in_progress"
                            for agent_id in run.agent_ids
                        ):
                            reason = "agent_in_progress"
                        if reason is None and run.agent_ids and all(
                            agent_blockers.get(agent_id) == "shift_ended"
                            for agent_id in run.agent_ids
                        ):
                            reason = "shift_ended"
                        reason = reason or "no_available_agents"
                    preflight[case.id] = ("unassigned", reason)
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
            fixed_agent = locked.get(case.id) or (None if case.id in movable_ids else case.assigned_agent_id)
            manual_override = manual_owners.get(case.id) == fixed_agent == case.assigned_agent_id
            if run.region_code != ALL_REGIONS and case.region_code != run.region_code and not manual_override:
                preflight[case_id] = ("unassigned", "region_mismatch")
                continue
            if case.status not in {"pending", "assigned"}:
                preflight[case_id] = ("unassigned", "status_not_assignable")
                continue
            if not case.location_confirmed:
                preflight[case_id] = ("unassigned", "location_unconfirmed")
                continue
            current = assignment_by_case.get(case.id)
            if current and fixed_agent != current.agent_id and case.id not in movable_ids:
                raise PlanningConflict("assignment_lock_conflict")
            if fixed_agent and fixed_agent not in {shift.agent_id for shift in eligible_agents}:
                preflight[case_id] = ("unassigned", "waiting_for_reassignment" if case.id in movable_ids else "unsafe_agent_origin")
                locked.pop(case.id, None)
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

        radius_eligible_agent_ids_by_case: dict[int, set[int]] = {}
        manual_locked_case_ids: set[int] = set()
        for case in cases:
            fixed_agent = locked.get(case.id) or (None if case.id in movable_ids else case.assigned_agent_id)
            if manual_owners.get(case.id) == fixed_agent == case.assigned_agent_id and fixed_agent is not None:
                manual_locked_case_ids.add(case.id)
                radius_eligible_agent_ids_by_case[case.id] = {fixed_agent}
                continue
            eligible_for_case = {
                shift.agent_id
                for shift in eligible_agents
                if shift.region_code in {case.region_code, ALL_REGIONS}
                and _case_within_service_radius(case, shift)
            }
            radius_eligible_agent_ids_by_case[case.id] = eligible_for_case
            if not eligible_for_case:
                preflight[case.id] = ("unassigned", "outside_service_radius")
        cases = [case for case in cases if radius_eligible_agent_ids_by_case.get(case.id)]
        if not cases:
            _record_ready_run(
                db, run, expected_input_digest, case_rows, shifts, agents,
                assignment_by_case, preflight, {},
            )
            return

        earliest_shift_start = min(_epoch(_planning_floor(shift, current_now)) for shift in used_shifts)
        latest_shift_end = max(_epoch(shift.shift_ends_at) for shift in used_shifts)
        impossible_windows = set()
        for case in cases:
            if case.visit_due_at and _epoch(case.visit_due_at) <= earliest_shift_start:
                preflight[case.id] = ("unassigned", "expired_visit_window")
                impossible_windows.add(case.id)
                continue
            earliest_start = _epoch_ceil(case.visit_not_before_at) if case.visit_not_before_at else earliest_shift_start
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
            origin_latitude, origin_longitude, _origin_label = _route_origin(shift, current_now)
            coordinate_for_case.add((round(origin_latitude, 6), round(origin_longitude, 6)))
            destination = _route_destination(shift)
            if destination is not None:
                end_latitude, end_longitude, _end_label = destination
                coordinate_for_case.add((round(end_latitude, 6), round(end_longitude, 6)))
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
        run.warnings = assignment_warnings + [
            {"type": "road_snap_distance", "latitude": coordinate[0], "longitude": coordinate[1], "distance_metres": distance}
            for coordinate, distance in snap_distances.items()
            if 500 < distance <= 2000
        ]
        valid_shifts: list[AgentShift] = []
        for shift in used_shifts:
            origin_latitude, origin_longitude, _origin_label = _route_origin(shift, current_now)
            start = (round(origin_latitude, 6), round(origin_longitude, 6))
            destination = _route_destination(shift)
            destination_is_routable = True
            if destination is not None:
                end_latitude, end_longitude, _end_label = destination
                end = (round(end_latitude, 6), round(end_longitude, 6))
                destination_is_routable = snap_distances.get(end, 0) <= 2000
            if snap_distances.get(start, 0) <= 2000 and destination_is_routable:
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

        # Keep only active origins, explicit end points, and case coordinates.
        coordinate_for_case = {(round(case.latitude, 6), round(case.longitude, 6)) for case in cases}
        for shift in used_shifts:
            origin_latitude, origin_longitude, _origin_label = _route_origin(shift, current_now)
            coordinate_for_case.add((round(origin_latitude, 6), round(origin_longitude, 6)))
            destination = _route_destination(shift)
            if destination is not None:
                end_latitude, end_longitude, _end_label = destination
                coordinate_for_case.add((round(end_latitude, 6), round(end_longitude, 6)))
        coordinates = sorted(coordinate_for_case)
        if len(coordinates) > min(80, PLANNING_MAX_LOCATIONS):
            raise PlanningConflict("run_too_large")
        point_indexes = {coordinate: index for index, coordinate in enumerate(coordinates)}
        table = osrm.table(coordinates)
        durations = table.get("durations") or []
        distances = table.get("distances") or []
        if not _valid_cost_matrix(durations, len(coordinates)) or not _valid_cost_matrix(distances, len(coordinates)):
            raise RoutingUnavailable("osrm_matrix_shape_invalid")

        # A manual assignment may intentionally exceed the normal depot-radius
        # rule, but an impossible same-day stop must not make the optimizer
        # discard every other locked stop on that vehicle. If even the shortest
        # required path from the current origin through the stop and back to an
        # explicit shift end (plus service) exceeds the remaining shift, retain
        # the manual assignment as unscheduled and optimize the feasible work.
        shift_by_agent = {shift.agent_id: shift for shift in used_shifts}
        manual_stops_beyond_shift: set[int] = set()
        for case in cases:
            if case.id not in manual_locked_case_ids:
                continue
            agent_id = locked.get(case.id) or case.assigned_agent_id
            shift = shift_by_agent.get(agent_id)
            if shift is None:
                continue
            origin_latitude, origin_longitude, _origin_label = _route_origin(shift, current_now)
            origin = point_indexes[(round(origin_latitude, 6), round(origin_longitude, 6))]
            case_point = point_indexes[(round(case.latitude, 6), round(case.longitude, 6))]
            travel_to_case = durations[origin][case_point]
            if travel_to_case is None or not isfinite(travel_to_case):
                continue
            minimum_required_seconds = travel_to_case + case.service_duration_seconds
            destination = _route_destination(shift)
            if destination is not None:
                end_latitude, end_longitude, _end_label = destination
                end = point_indexes[(round(end_latitude, 6), round(end_longitude, 6))]
                travel_to_end = durations[case_point][end]
                if travel_to_end is None or not isfinite(travel_to_end):
                    continue
                minimum_required_seconds += travel_to_end
            remaining_shift_seconds = _epoch(shift.shift_ends_at) - _epoch(
                _planning_floor(shift, current_now)
            )
            if minimum_required_seconds > remaining_shift_seconds:
                manual_stops_beyond_shift.add(case.id)
                preflight[case.id] = ("unassigned", "manual_stop_exceeds_shift")
        cases = [case for case in cases if case.id not in manual_stops_beyond_shift]
        if not cases:
            _record_ready_run(
                db, run, expected_input_digest, case_rows, shifts, agents,
                assignment_by_case, preflight, {},
            )
            return

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
                if point_indexes[(round(_route_origin(shift, current_now)[0], 6), round(_route_origin(shift, current_now)[1], 6))] in component
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
                now=current_now,
                radius_eligible_agent_ids_by_case=radius_eligible_agent_ids_by_case,
                manual_locked_case_ids=manual_locked_case_ids,
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
                is_unscheduled_for_constraints = bool(
                    result
                    and result.get("outcome") == "unassigned"
                    and result.get("reason") == "no_feasible_route_under_constraints"
                )
                if case_id not in manual_locked_case_ids and not is_unscheduled_for_constraints:
                    raise PlanningConflict("locked_case_not_feasible")
        for case_id in run.investigation_ids:
            item = outcome_by_case.get(case_id)
            if item:
                if case_id in movable_ids and item.get("outcome") == "unassigned":
                    item["reason"] = "waiting_for_reassignment"
                preflight[case_id] = (item["outcome"], item.get("reason"))
                if item.get("agent_id") is not None:
                    preflight[case_id] = ("assigned", None)

        priority_order_warnings = [
            warning
            for outcome in outcomes
            for warning in outcome.pop("_priority_order_warnings", [])
        ]
        run.warnings = [
            warning for warning in (run.warnings or [])
            if warning.get("type") != "priority_order"
        ] + priority_order_warnings
        db.flush()

        route_geometries = _build_route_geometries(osrm, case_rows, shifts, outcome_by_case, current_now)
        _record_ready_run(db, run, expected_input_digest, case_rows, shifts, agents, assignment_by_case, preflight, outcome_by_case, route_geometries)
    except Exception as error:
        if not isinstance(error, (PlanningConflict, RoutingUnavailable)):
            # The database record deliberately keeps a stable public error
            # code. Preserve the traceback in worker logs so unexpected planner
            # failures can be diagnosed without silently masking the cause.
            logger.exception(
                "Unexpected exception while optimizing planning run %s",
                run_id,
            )
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
    rows_by_agent: dict[int, list[tuple[PlanningItem, Investigation]]] = {}
    for item, case, _assigned_agent in items:
        if item.outcome == "assigned" and item.agent_id is not None:
            rows_by_agent.setdefault(item.agent_id, []).append((item, case))
    route_responses = [
        route_response_through_last_stop(
            route,
            agent,
            shift_by_agent.get(agent.id),
            sorted(
                rows_by_agent.get(agent.id, []),
                key=lambda row: (row[0].sequence or 0, row[1].id),
            ),
        )
        for route, agent in routes
    ]
    return {
        "routes": route_responses,
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
                "reopen_on": case.reopen_on.isoformat() if case.reopen_on else None,
                "prior_agent_id": case.assigned_agent_id,
                "service_duration_seconds": case.service_duration_seconds,
                "agent_id": item.agent_id,
                "agent_name": agent.name if agent else None,
                "outcome": item.outcome,
                "reason": item.reason,
                "sequence": item.sequence,
                "estimated_arrival_at": item.estimated_arrival_at,
                "earliest_arrival_estimate_at": item.estimated_arrival_at,
                "planned_arrival_at": item.planned_arrival_at,
                "estimated_service_start_at": item.estimated_service_start_at,
                "waiting_seconds": item.waiting_seconds if item.planned_arrival_at is not None else None,
                "planned_waiting_seconds": item.waiting_seconds if item.planned_arrival_at is not None else None,
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
    apply_now = _database_now(db)
    assigned_agents = {item.agent_id for item in items if item.outcome == "assigned" and item.agent_id is not None}
    if assigned_agents and not _geometry_complete(db, run.id, assigned_agents):
        raise PlanningConflict("route_geometry_incomplete")

    locked = {item["investigation_id"]: item["agent_id"] for item in run.locked_assignments}
    assignments = {
        assignment.investigation_id: assignment
        for assignment in db.query(InvestigationAssignment)
        .filter(InvestigationAssignment.investigation_id.in_(case_ids), InvestigationAssignment.is_active.is_(True))
        .with_for_update()
        .all()
    }
    manual_locked_case_ids = {
        investigation_id
        for investigation_id, assignment in assignments.items()
        if assignment.assignment_source == "manual"
        and locked.get(investigation_id) == assignment.agent_id
    }
    movable_case_ids = set(run.movable_investigation_ids or [])
    assignment_owner_ids = {
        assignment.agent_id for assignment in assignments.values()
        if assignment.investigation_id in movable_case_ids
    }
    assignment_owner_shifts = {
        shift.agent_id: shift
        for shift in db.query(AgentShift).filter(
            AgentShift.agent_id.in_(assignment_owner_ids),
            AgentShift.work_date == run.work_date,
        ).all()
    } if assignment_owner_ids else {}
    sequence_keys: set[tuple[int, int]] = set()

    # Apply is all-or-nothing. Every proposed stop is rechecked under the locks above.
    for item in items:
        if item.outcome == "unassigned":
            preserved_assignment = item.reason in {
                "no_available_agents", "locked_agent_unavailable", "unsafe_agent_origin", "waiting_for_reassignment",
                "agent_in_progress", "shift_ended", "agent_not_eligible", "agent_shift_unavailable",
                "agent_region_mismatch", "no_routable_agent_start", "no_feasible_route_under_constraints",
            }
            preserved_assignment = preserved_assignment or (
                item.investigation_id in manual_locked_case_ids and item.reason is not None
            )
            if item.agent_id is not None or item.sequence is not None or (item.investigation_id in locked and not preserved_assignment):
                raise PlanningConflict("planning_result_invalid")
            continue
        if item.outcome != "assigned" or item.agent_id is None or item.sequence is None or item.sequence < 1:
            raise PlanningConflict("planning_result_invalid")
        if item.travel_seconds is None or item.travel_seconds < 0 or item.travel_metres is None or item.travel_metres < 0:
            raise PlanningConflict("planning_result_invalid")
        if item.estimated_arrival_at is None:
            raise PlanningConflict("planning_result_invalid")
        if item.planned_arrival_at is not None:
            if item.waiting_seconds is None or item.estimated_service_start_at is None:
                raise PlanningConflict("planning_result_invalid")
            expected_service_start = _as_utc(item.planned_arrival_at) + timedelta(
                seconds=item.waiting_seconds,
            )
            if _as_utc(item.estimated_service_start_at) != expected_service_start:
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
        service_start = _as_utc(item.estimated_service_start_at or item.estimated_arrival_at)
        end = _as_utc(shift.shift_ends_at)
        floor = _planning_floor(shift, apply_now)
        if service_start < floor or service_start.timestamp() + case.service_duration_seconds > end.timestamp():
            raise PlanningConflict("agent_schedule_changed")
        if shift.break_starts_at and shift.break_ends_at and service_start < _as_utc(shift.break_ends_at) and service_start.timestamp() + case.service_duration_seconds > _as_utc(shift.break_starts_at).timestamp():
            raise PlanningConflict("agent_break_changed")
        if case.visit_not_before_at and service_start < _as_utc(case.visit_not_before_at):
            raise PlanningConflict("visit_window_changed")
        if case.visit_due_at and service_start.timestamp() + case.service_duration_seconds > _as_utc(case.visit_due_at).timestamp():
            raise PlanningConflict("visit_window_changed")
        current_assignment = assignments.get(case.id)
        manual_override = bool(
            current_assignment
            and current_assignment.assignment_source == "manual"
            and current_assignment.agent_id == item.agent_id
            and case.assigned_agent_id == item.agent_id
        )
        if not manual_override and not _case_within_service_radius(case, shift):
            raise PlanningConflict("service_radius_changed")

    for item in items:
        if item.outcome == "unassigned":
            current = assignments.get(item.investigation_id)
            case = case_by_id.get(item.investigation_id)
            owner_shift = assignment_owner_shifts.get(current.agent_id) if current else None
            if (
                case is not None
                and current is not None
                and current.assignment_source == "automatic"
                and item.investigation_id in movable_case_ids
                and case.assigned_agent_id == current.agent_id
                and owner_shift is not None
                and not _case_within_service_radius(case, owner_shift)
            ):
                current.is_active = False
                current.unassigned_at = datetime.now(timezone.utc)
                case.assigned_agent_id = None
                if case.status == "assigned":
                    case.status = "pending"
                db.add(ActivityLog(
                    actor_id=actor.id,
                    action="investigation.automatic_assignment_removed_outside_service_radius",
                    object_type="investigation",
                    object_id=case.id,
                    details={
                        "planning_run_id": run.id,
                        "previous_agent_id": current.agent_id,
                        "service_radius_metres": DEFAULT_SERVICE_RADIUS_METRES,
                    },
                ))
            continue
        if item.outcome != "assigned" or item.agent_id is None:
            continue
        case = case_by_id[item.investigation_id]
        agent = agent_by_id.get(item.agent_id)
        shift = shift_by_agent.get(item.agent_id)
        if case.deleted_at is not None or case.status not in {"pending", "assigned"}:
            raise PlanningConflict("case_no_longer_assignable")
        if not agent or agent.role != "agent" or not agent.is_active or not shift or not shift.is_available:
            raise PlanningConflict("agent_no_longer_eligible")
        manual_override = bool(
            assignments.get(case.id)
            and assignments[case.id].assignment_source == "manual"
            and assignments[case.id].agent_id == item.agent_id
            and case.assigned_agent_id == item.agent_id
        )
        if (run.region_code != ALL_REGIONS and shift.region_code not in {run.region_code, ALL_REGIONS}) or (run.region_code != ALL_REGIONS and case.region_code != run.region_code and not manual_override):
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

    for item in items:
        if item.outcome != "assigned" or item.agent_id is None:
            continue
        case = case_by_id[item.investigation_id]
        agent = agent_by_id[item.agent_id]
        current = assignments.get(case.id)
        if current and current.agent_id != agent.id:
            if (
                case.id not in movable_case_ids
                or current.assignment_source != "automatic"
            ):
                raise PlanningConflict("assignment_changed")
            current.is_active = False
            current.unassigned_at = datetime.now(timezone.utc)
            db.flush()
            assignment = InvestigationAssignment(
                investigation_id=case.id,
                agent_id=agent.id,
                assigned_by_id=actor.id,
                assignment_source="automatic",
                note=f"Automatic reassignment from unavailable agent in planning run {run.id}",
            )
            case.assigned_agent_id = agent.id
            case.status = "assigned"
            db.add(assignment)
            db.flush()
            item.applied_assignment_id = assignment.id
            current = assignment
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

    routed_case_agents = {
        item.investigation_id: item.agent_id
        for item in items
        if item.outcome == "assigned" and item.agent_id is not None
    }
    if routed_case_agents:
        revisit_requests = db.query(AgentRevisitRequest).filter(
            AgentRevisitRequest.investigation_id.in_(routed_case_agents),
            AgentRevisitRequest.target_work_date == run.work_date,
            AgentRevisitRequest.status == "queued",
        ).with_for_update().all()
        for request in revisit_requests:
            if routed_case_agents.get(request.investigation_id) == request.agent_id:
                request.status = "routed"
                request.planning_run_id = run.id

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

