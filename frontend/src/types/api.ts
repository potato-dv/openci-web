export type UserRole = "admin" | "supervisor" | "agent";

export type InvestigationStatus =
  | "pending"
  | "assigned"
  | "in_progress"
  | "under_review"
  | "returned_for_correction"
  | "completed";

export type InvestigationPriority = "normal" | "high" | "urgent";
export type VisitOutcome = "visited" | "no_access" | "unable_to_locate";
export type InvestigationOutcome =
  "verified" | "not_verified" | "unable_to_verify" | "inconclusive";
export type OccupancyStatus =
  "occupied" | "vacant" | "unknown" | "not_applicable";
export type ReportStatus =
  "draft" | "submitted" | "approved" | "returned_for_correction";
export type ReviewDecision = "approved" | "returned_for_correction";

export type User = {
  id: number;
  name: string;
  email: string;
  role: UserRole;
  is_active: boolean;
};

export type NewUser = {
  name: string;
  email: string;
  password: string;
  role: UserRole;
};

export type Investigation = {
  id: number;
  reference_number: string;
  first_name: string | null;
  middle_name: string | null;
  last_name: string | null;
  subject_name: string;
  legacy_address: string | null;
  address_display: string;
  house_number: string | null;
  unit_floor_building_name: string | null;
  street: string | null;
  subdivision_village_purok: string | null;
  region_code: string | null;
  province_code: string | null;
  city_municipality_code: string | null;
  barangay_code: string | null;
  postal_code: string | null;
  status: InvestigationStatus;
  priority: InvestigationPriority;
  assigned_agent_id?: number | null;
  assigned_agent_name?: string | null;
  created_at?: string;
  location_confirmed?: boolean;
  location_confirmed_at?: string | null;
  service_duration_seconds?: number;
  visit_not_before_at?: string | null;
  visit_due_at?: string | null;
};

export type NewInvestigation = {
  first_name: string;
  middle_name: string | null;
  last_name: string;
  house_number: string;
  unit_floor_building_name: string;
  street: string;
  subdivision_village_purok: string;
  region_code: string;
  province_code: string;
  city_municipality_code: string;
  barangay_code: string;
  postal_code: string;
  priority: InvestigationPriority;
  service_duration_seconds: number;
  visit_not_before_at: string | null;
  visit_due_at: string | null;
};

export type InvestigationUpdate = {
  first_name?: string;
  middle_name?: string | null;
  last_name?: string;
  house_number?: string;
  unit_floor_building_name?: string | null;
  street?: string;
  subdivision_village_purok?: string | null;
  region_code?: string;
  province_code?: string | null;
  city_municipality_code?: string;
  barangay_code?: string;
  postal_code?: string | null;
  priority?: InvestigationPriority;
  service_duration_seconds?: number;
  visit_not_before_at?: string | null;
  visit_due_at?: string | null;
};

export type LocationOption = { code: string; name: string; type?: string };
export type GeocodeCandidate = {
  label: string;
  category: string | null;
  latitude: number;
  longitude: number;
  provider_ref: string | null;
};
export type InvestigationLocation = {
  latitude: number;
  longitude: number;
  source: "nominatim" | "manual";
  provider_ref: string | null;
  confirmed_at: string;
  h3_r7: string;
  h3_r8: string;
  h3_r9: string;
};
export type AgentShiftInput = {
  work_date: string;
  region_code: string;
  is_available: boolean;
  shift_starts_at: string;
  shift_ends_at: string;
  start_latitude: number;
  start_longitude: number;
  end_latitude?: number | null;
  end_longitude?: number | null;
  start_location_label?: string | null;
  start_location_source?: "manual" | "nominatim" | null;
  start_location_provider_ref?: string | null;
  end_location_label?: string | null;
  end_location_source?: "manual" | "nominatim" | null;
  end_location_provider_ref?: string | null;
  max_visits: number;
  max_open_cases: number;
};
export type AgentShift = AgentShiftInput & {
  id: number;
  agent_id: number;
  current_planning_run_id: number | null;
};
export type PlanningAgent = {
  start: RoutePoint;
  end: RoutePoint | null;
  id: number;
  name: string;
  region_code: string;
  shift_id: number;
  shift_starts_at: string;
  shift_ends_at: string;
  max_visits: number;
  max_open_cases: number;
  open_case_count: number;
  current_planning_run_id: number | null;
};
export type PlanningCase = {
  service_duration_seconds?: number;
  latitude: number;
  longitude: number;
  assigned_agent_id: number | null;
  assigned_agent_name?: string | null;
  id: number;
  reference_number: string;
  status: InvestigationStatus;
  priority: InvestigationPriority;
  address_display: string;
  location_confirmed: boolean;
};
export type PlanningReadiness = {
  work_date: string;
  region_code: string;
  resolution: 7 | 8 | 9;
  active_agent_count: number;
  unavailable_agent_count: number;
  eligible_cases: PlanningCase[];
  available_agents: PlanningAgent[];
  excluded_cases: {
    id: number;
    reference_number: string;
    reason: string;
    assigned_agent_id?: number | null;
    assigned_agent_name?: string | null;
  }[];
  density: { cell: string; count: number; geometry: PolygonGeometry }[];
};
export type PlanningMapData = {
  work_date: string;
  region_code: string | null;
  investigations: {
    id: number;
    reference_number: string;
    address_display: string;
    latitude: number;
    longitude: number;
    priority: InvestigationPriority;
    status: InvestigationStatus;
    region_code: string | null;
    assigned_agent_id: number | null;
    assigned_agent_name: string | null;
    service_duration_seconds: number;
    visit_not_before_at: string | null;
    visit_due_at: string | null;
  }[];
  agents: {
    id: number;
    name: string;
    is_active: boolean;
    region_code: string | null;
    is_available: boolean | null;
    shift_starts_at: string | null;
    shift_ends_at: string | null;
    start: RoutePoint | null;
  }[];
  unlocated_investigations: {
    id: number;
    reference_number: string;
    status: InvestigationStatus;
    region_code: string | null;
  }[];
  unlocated_agents: { id: number; name: string; is_active: boolean }[];
};
export type PlanningDashboard = {
  work_date: string;
  region_code: string | null;
  total_investigations: number;
  automatically_assigned: number;
  unassigned_investigations: number;
  active_agents: number;
  available_agents: number;
  optimizing_routes: number;
  published_routes: number;
  failed_planning_jobs: number;
  investigation_states: {
    investigation_id: number;
    planning_status: "pending" | "optimizing" | "assigned" | "unassigned" | "failed";
    reason: string | null;
    planning_run_id: number | null;
    assignment_source: "automatic" | "manual" | null;
  }[];
};
export type PlanningDependency =
  | "dataset_unconfigured"
  | "worker_unavailable"
  | "osrm_unavailable"
  | "vroom_unavailable";
export type PlanningServiceStatus = {
  ready: boolean;
  checked_at: string;
  dataset_version: string | null;
  dependencies: {
    dataset: "ready" | "unconfigured";
    worker: "ready" | "unavailable";
    osrm: "ready" | "unavailable";
    vroom: "ready" | "unavailable";
  };
  blocking_reasons: PlanningDependency[];
};
export type PlanningItem = {
  service_duration_seconds?: number;
  latitude: number | null;
  longitude: number | null;
  priority: InvestigationPriority;
  status: InvestigationStatus;
  prior_agent_id: number | null;
  investigation_id: number;
  reference_number: string;
  address_display: string;
  agent_id: number | null;
  agent_name: string | null;
  outcome: "assigned" | "unassigned";
  reason: string | null;
  sequence: number | null;
  estimated_arrival_at: string | null;
  travel_seconds: number | null;
  travel_metres: number | null;
};
export type PlanningRun = {
  auto_publish?: boolean;
  routes: PlanningRouteGeometry[];
  geometry_complete: boolean;
  investigation_ids: number[];
  agent_ids: number[];
  id: number;
  work_date: string;
  region_code: string;
  status: "queued" | "running" | "ready" | "failed" | "stale" | "applied";
  result_digest: string | null;
  error_code: string | null;
  osrm_dataset: string | null;
  created_at: string;
  finished_at: string | null;
  applied_at: string | null;
  warnings: {
    type: string;
    latitude: number;
    longitude: number;
    distance_metres: number;
  }[];
  items: PlanningItem[];
};
export type RoutePoint = {
  latitude: number;
  longitude: number;
  label?: string | null;
};
export type LineStringGeometry = {
  type: "LineString";
  coordinates: [number, number][];
};
export type PolygonGeometry = {
  type: "Polygon";
  coordinates: [number, number][][];
};
export type PlanningRouteGeometry = {
  shift?: AgentShift | null;
  agent_id: number;
  agent_name: string;
  geometry_status: "ready" | "failed";
  geometry_error_code: string | null;
  geometry: LineStringGeometry | null;
  geometry_digest: string | null;
  total_distance_metres: number | null;
  total_travel_seconds: number | null;
  start: RoutePoint;
  end: RoutePoint | null;
};
export type AgentRoute = {
  work_date: string;
  reason:
    | "no_shift"
    | "shift_unavailable"
    | "no_published_stops"
    | "route_refresh_pending"
    | "route_needs_refresh"
    | null;
  shift: AgentShift | null;
  route: PlanningRouteGeometry | null;
  stops: {
    service_duration_seconds: number;
    investigation_id: number;
    reference_number: string;
    address_display: string;
    sequence: number | null;
    estimated_arrival_at: string | null;
    travel_seconds: number | null;
    travel_metres: number | null;
    latitude: number;
    longitude: number;
    priority: InvestigationPriority;
    status: InvestigationStatus;
  }[];
};
export type PlanningRouteOverviewAgent = {
  id: number;
  name: string;
  is_active: boolean;
  region_code: string | null;
  shift: AgentShift | null;
  route_status:
    | "none"
    | "queued"
    | "running"
    | "published"
    | "failed"
    | "partially_published"
    | "needs_refresh";
  refresh_errors: string[];
  refresh_investigation_id: number | null;
  run_id: number | null;
  planning_status: "idle" | "queued" | "running" | "failed";
  planning_error_code: string | null;
  planning_run_id: number | null;
  open_case_count: number;
  remaining_open_capacity: number | null;
  route: PlanningRouteGeometry | null;
  stops: AgentRoute["stops"];
};
export type PlanningRouteOverview = {
  work_date: string;
  region_code: string | null;
  agents: PlanningRouteOverviewAgent[];
};
export type AgentRosterRow = {
  agent: User;
  shift: AgentShift | null;
  assigned_workload_count: number;
  visit_workload_count: number;
};
export type PageResult<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};
export type InvestigationPage = PageResult<Investigation> & {
  facets: {
    status: Record<InvestigationStatus, number>;
    priority: Record<InvestigationPriority, number>;
    assigned: number;
    unassigned: number;
    location_unconfirmed: number;
  };
};
export type ReportQueueItem = {
  report_id: number;
  investigation_id: number;
  reference_number: string;
  subject_name: string;
  assigned_agent_name: string | null;
  author_name: string;
  version: number;
  priority: InvestigationPriority;
  status: ReportStatus;
  submitted_at: string | null;
  updated_at: string;
};
export type ActivityLog = {
  id: number;
  actor_id: number | null;
  actor_name: string | null;
  action: string;
  object_type: string;
  object_id: number | null;
  details: Record<string, unknown>;
  created_at: string;
};

export type Assignment = {
  id: number;
  investigation_id: number;
  agent_id: number;
  agent_name: string;
  assigned_by_id: number;
  assigned_by_name: string;
  assignment_source: "automatic" | "manual";
  note: string | null;
  is_active: boolean;
  assigned_at: string;
  unassigned_at: string | null;
  route_refresh?: AssignmentRouteRefresh | null;
};

export type AssignmentRouteRefresh = {
  status: "queued" | "running" | "published" | "failed" | "partially_published";
  work_date: string;
  agent_ids: number[];
  run_ids: number[];
  errors: string[];
};

export type Report = {
  id: number;
  investigation_id: number;
  author_id: number;
  author_name: string;
  version: number;
  content: string;
  visit_outcome: VisitOutcome | null;
  outcome: InvestigationOutcome | null;
  verified_address: string | null;
  occupancy_status: OccupancyStatus | null;
  property_condition: string | null;
  interaction_notes: string | null;
  visited_at: string | null;
  status: ReportStatus;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
};

export type ReportInput = {
  content: string;
  visit_outcome: VisitOutcome | null;
  outcome: InvestigationOutcome | null;
  verified_address: string | null;
  occupancy_status: OccupancyStatus | null;
  property_condition: string | null;
  interaction_notes: string | null;
  visited_at: string | null;
};

export type Review = {
  id: number;
  investigation_id: number;
  report_id: number;
  reviewer_id: number;
  reviewer_name: string;
  decision: ReviewDecision;
  comments: string | null;
  reviewed_at: string;
};

export type LoginResponse = {
  access_token: string;
  token_type: "bearer";
};
