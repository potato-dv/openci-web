from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.user import UserResponse


class LocationConfirm(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    source: Literal["nominatim", "manual"]
    provider_ref: str | None = Field(default=None, max_length=100)


class LocationResponse(BaseModel):
    latitude: float
    longitude: float
    source: str
    provider_ref: str | None
    confirmed_at: datetime
    h3_r7: str
    h3_r8: str
    h3_r9: str


class GeocodeCandidate(BaseModel):
    label: str
    category: str | None = None
    latitude: float
    longitude: float
    provider_ref: str | None = None


class AgentShiftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_date: date
    region_code: str = Field(min_length=10, max_length=10)
    is_available: bool = True
    shift_starts_at: datetime
    shift_ends_at: datetime
    start_latitude: float = Field(ge=-90, le=90)
    start_longitude: float = Field(ge=-180, le=180)
    end_latitude: float | None = Field(default=None, ge=-90, le=90)
    end_longitude: float | None = Field(default=None, ge=-180, le=180)
    start_location_label: str | None = Field(default=None, max_length=500)
    start_location_source: Literal["manual", "nominatim"] | None = None
    start_location_provider_ref: str | None = Field(default=None, max_length=100)
    end_location_label: str | None = Field(default=None, max_length=500)
    end_location_source: Literal["manual", "nominatim"] | None = None
    end_location_provider_ref: str | None = Field(default=None, max_length=100)
    max_visits: int = Field(ge=1, le=50)
    max_open_cases: int = Field(ge=1, le=200)

    @model_validator(mode="after")
    def validate_shift(self):
        if self.shift_starts_at.tzinfo is None or self.shift_ends_at.tzinfo is None:
            raise ValueError("Shift timestamps must include a timezone offset")
        if self.shift_ends_at <= self.shift_starts_at:
            raise ValueError("Shift end must be after shift start")
        if (self.end_latitude is None) != (self.end_longitude is None):
            raise ValueError("End latitude and longitude must be supplied together")
        for prefix in ("start", "end"):
            source = getattr(self, f"{prefix}_location_source")
            ref = getattr(self, f"{prefix}_location_provider_ref")
            if ref and source != "nominatim":
                raise ValueError("Provider references require a Nominatim location")
        return self


class AgentShiftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: int
    work_date: date
    region_code: str
    is_available: bool
    shift_starts_at: datetime
    shift_ends_at: datetime
    start_latitude: float
    start_longitude: float
    end_latitude: float | None
    end_longitude: float | None
    start_location_label: str | None = Field(default=None, max_length=500)
    start_location_source: Literal["manual", "nominatim"] | None = None
    start_location_provider_ref: str | None = Field(default=None, max_length=100)
    end_location_label: str | None = Field(default=None, max_length=500)
    end_location_source: Literal["manual", "nominatim"] | None = None
    end_location_provider_ref: str | None = Field(default=None, max_length=100)
    max_visits: int
    max_open_cases: int
    current_planning_run_id: int | None


class LockedAssignment(BaseModel):
    investigation_id: int = Field(gt=0)
    agent_id: int = Field(gt=0)


class PlanningRunCreate(BaseModel):
    work_date: date
    region_code: str = Field(min_length=10, max_length=10)
    investigation_ids: list[int] = Field(min_length=1, max_length=80)
    agent_ids: list[int] = Field(max_length=200)
    locked_assignments: list[LockedAssignment] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_ids(self):
        if any(value < 1 for value in [*self.investigation_ids, *self.agent_ids]):
            raise ValueError("IDs must be positive")
        if len(set(self.investigation_ids)) != len(self.investigation_ids):
            raise ValueError("Investigation IDs must be unique")
        if len(set(self.agent_ids)) != len(self.agent_ids):
            raise ValueError("Agent IDs must be unique")
        if len({item.investigation_id for item in self.locked_assignments}) != len(self.locked_assignments):
            raise ValueError("Each investigation can have only one locked agent")
        if any(item.investigation_id not in self.investigation_ids for item in self.locked_assignments):
            raise ValueError("Locked investigations must be included in the run")
        if any(item.agent_id not in self.agent_ids for item in self.locked_assignments):
            raise ValueError("Locked agents must be included in the run")
        return self


class PlanningItemResponse(BaseModel):
    service_duration_seconds: int = 2700
    investigation_id: int
    reference_number: str
    address_display: str
    latitude: float | None = None
    longitude: float | None = None
    priority: str = "normal"
    status: str = "pending"
    prior_agent_id: int | None = None
    agent_id: int | None
    agent_name: str | None
    outcome: Literal["assigned", "unassigned"]
    reason: str | None
    sequence: int | None
    estimated_arrival_at: datetime | None
    travel_seconds: int | None
    travel_metres: int | None


class RoutePoint(BaseModel):
    latitude: float
    longitude: float
    label: str | None = None


class LineStringGeometry(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[tuple[float, float]] = Field(min_length=2)


class PolygonGeometry(BaseModel):
    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[tuple[float, float]]]


class PlanningRouteResponse(BaseModel):
    shift: AgentShiftResponse | None = None
    agent_id: int
    agent_name: str
    geometry_status: Literal["ready", "failed"]
    geometry_error_code: str | None
    geometry: LineStringGeometry | None
    geometry_digest: str | None
    total_distance_metres: int | None
    total_travel_seconds: int | None
    start: RoutePoint
    end: RoutePoint | None


class PlanningRunResponse(BaseModel):
    id: int
    auto_publish: bool = False
    work_date: date
    region_code: str
    status: Literal["queued", "running", "ready", "failed", "stale", "applied"]
    result_digest: str | None
    error_code: str | None
    osrm_dataset: str | None
    created_at: datetime
    finished_at: datetime | None
    applied_at: datetime | None
    items: list[PlanningItemResponse] = Field(default_factory=list)
    warnings: list[dict] = Field(default_factory=list)
    routes: list[PlanningRouteResponse] = Field(default_factory=list)
    geometry_complete: bool = False
    investigation_ids: list[int] = Field(default_factory=list)
    agent_ids: list[int] = Field(default_factory=list)


PlanningDependency = Literal[
    "dataset_unconfigured",
    "worker_unavailable",
    "osrm_unavailable",
    "vroom_unavailable",
]


class PlanningDependencyStates(BaseModel):
    dataset: Literal["ready", "unconfigured"]
    worker: Literal["ready", "unavailable"]
    osrm: Literal["ready", "unavailable"]
    vroom: Literal["ready", "unavailable"]


class PlanningServiceStatusResponse(BaseModel):
    ready: bool
    checked_at: datetime
    dataset_version: str | None
    dependencies: PlanningDependencyStates
    blocking_reasons: list[PlanningDependency]


class PlanningCaseResponse(BaseModel):
    service_duration_seconds: int = 2700
    id: int
    reference_number: str
    status: str
    priority: str
    address_display: str
    location_confirmed: bool
    latitude: float
    longitude: float
    assigned_agent_id: int | None = None
    assigned_agent_name: str | None = None
    visit_not_before_at: datetime | None = None
    visit_due_at: datetime | None = None


class PlanningAgentResponse(BaseModel):
    id: int
    name: str
    region_code: str
    shift_id: int
    shift_starts_at: datetime
    shift_ends_at: datetime
    max_visits: int
    max_open_cases: int
    open_case_count: int
    current_planning_run_id: int | None
    start: RoutePoint
    end: RoutePoint | None


class ExcludedCaseResponse(BaseModel):
    id: int
    reference_number: str
    reason: str
    assigned_agent_id: int | None = None
    assigned_agent_name: str | None = None


class DensityCellResponse(BaseModel):
    cell: str
    count: int
    geometry: PolygonGeometry


class PlanningReadinessResponse(BaseModel):
    work_date: date
    region_code: str
    resolution: Literal[7, 8, 9]
    active_agent_count: int
    unavailable_agent_count: int
    eligible_cases: list[PlanningCaseResponse]
    available_agents: list[PlanningAgentResponse]
    excluded_cases: list[ExcludedCaseResponse]
    density: list[DensityCellResponse]


class PlanningMapInvestigationResponse(BaseModel):
    id: int
    reference_number: str
    address_display: str
    latitude: float
    longitude: float
    priority: str
    status: str
    region_code: str | None
    assigned_agent_id: int | None
    assigned_agent_name: str | None
    service_duration_seconds: int = 2700
    visit_not_before_at: datetime | None = None
    visit_due_at: datetime | None = None


class PlanningMapAgentResponse(BaseModel):
    id: int
    name: str
    is_active: bool
    region_code: str | None
    is_available: bool | None
    shift_starts_at: datetime | None
    shift_ends_at: datetime | None
    start: RoutePoint | None


class PlanningMapUnlocatedInvestigationResponse(BaseModel):
    id: int
    reference_number: str
    status: str
    region_code: str | None


class PlanningMapUnlocatedAgentResponse(BaseModel):
    id: int
    name: str
    is_active: bool


class PlanningMapDataResponse(BaseModel):
    work_date: date
    region_code: str | None
    investigations: list[PlanningMapInvestigationResponse]
    agents: list[PlanningMapAgentResponse]
    unlocated_investigations: list[PlanningMapUnlocatedInvestigationResponse]
    unlocated_agents: list[PlanningMapUnlocatedAgentResponse]


class AgentRouteStop(BaseModel):
    service_duration_seconds: int = 2700
    investigation_id: int
    reference_number: str
    address_display: str
    sequence: int | None
    estimated_arrival_at: datetime | None
    travel_seconds: int | None
    travel_metres: int | None
    latitude: float
    longitude: float
    priority: str
    status: str


class PlanningRouteOverviewAgentResponse(BaseModel):
    id: int
    name: str
    is_active: bool
    region_code: str | None = None
    shift: AgentShiftResponse | None = None
    route_status: Literal[
        "none", "queued", "running", "published", "failed",
        "partially_published", "needs_refresh",
    ] = "none"
    refresh_errors: list[str] = Field(default_factory=list)
    refresh_investigation_id: int | None = None
    run_id: int | None = None
    planning_status: Literal["idle", "queued", "running", "failed"] = "idle"
    planning_error_code: str | None = None
    planning_run_id: int | None = None
    open_case_count: int = 0
    remaining_open_capacity: int | None = None
    route: PlanningRouteResponse | None = None
    stops: list[AgentRouteStop] = Field(default_factory=list)


class PlanningRouteOverviewResponse(BaseModel):
    work_date: date
    region_code: str | None
    agents: list[PlanningRouteOverviewAgentResponse]


class PlanningDashboardCaseState(BaseModel):
    investigation_id: int
    planning_status: Literal["pending", "optimizing", "assigned", "unassigned", "failed"]
    reason: str | None = None
    planning_run_id: int | None = None
    assignment_source: Literal["automatic", "manual"] | None = None


class PlanningDashboardResponse(BaseModel):
    work_date: date
    region_code: str | None
    total_investigations: int
    automatically_assigned: int
    unassigned_investigations: int
    active_agents: int
    available_agents: int
    optimizing_routes: int
    published_routes: int
    failed_planning_jobs: int
    investigation_states: list[PlanningDashboardCaseState] = Field(default_factory=list)


class AgentRouteResponse(BaseModel):
    work_date: date
    reason: Literal[
        "no_shift", "shift_unavailable", "no_published_stops",
        "route_refresh_pending", "route_needs_refresh",
    ] | None = None
    shift: AgentShiftResponse | None = None
    route: PlanningRouteResponse | None = None
    stops: list[AgentRouteStop] = Field(default_factory=list)


class AgentRosterResponse(BaseModel):
    agent: UserResponse
    shift: AgentShiftResponse | None
    assigned_workload_count: int
    visit_workload_count: int
