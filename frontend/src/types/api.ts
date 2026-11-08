export type UserRole = "admin" | "supervisor" | "agent";

export type AgentFeatureCode =
  | "investigation.request_revisit"
  | "route.view_own_history"
  | "investigation.view_own_history";
export type AgentPermissions = Record<AgentFeatureCode, boolean>;
export type AgentPermissionEffect = "allow" | "deny" | "inherit";
export type AgentPermissionFeature = {
  code: AgentFeatureCode;
  name: string;
  description: string;
  default_allowed: boolean;
  override: "allow" | "deny" | null;
  effective_allowed: boolean;
};
export type AgentPermissionState = {
  agent: { id: number; name: string; is_active: boolean };
  features: AgentPermissionFeature[];
  mandatory_workflows: { name: string; description: string }[];
};
export type AgentPermissionHistoryItem = {
  id: number;
  actor_name: string | null;
  created_at: string;
  old_overrides: Record<string, "allow" | "deny" | "inherit">;
  new_overrides: Record<string, "allow" | "deny" | "inherit">;
  old_effective: Record<string, boolean>;
  new_effective: Record<string, boolean>;
};

export type InvestigationStatus =
  | "pending"
  | "assigned"
  | "in_progress"
  | "under_review"
  | "returned_for_correction"
  | "completed"
  | "cancelled";

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
  reopen_on?: string | null;
  priority: InvestigationPriority;
  assigned_agent_id?: number | null;
  assigned_agent_name?: string | null;
  manual_assignment_required?: boolean;
  created_at?: string;
  location_confirmed?: boolean;
  location_confirmed_at?: string | null;
  service_duration_seconds?: number;
  visit_not_before_at?: string | null;
  visit_due_at?: string | null;
  active_no_contact_event?: NoContactEventSummary | null;
};
export type NoContactEventSummary = {
  event_id: number;
  reason: string;
  notes: string | null;
  state: "deferred" | "retrying" | "retry_failed";
  retry_number: number;
  attempted_at: string;
  work_date: string;
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
  break_starts_at?: string | null;
  break_ends_at?: string | null;
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
  source?: "manual" | "recurring";
  schedule_version_id?: number | null;
  last_completed_investigation_id?: number | null;
  last_completed_report_id?: number | null;
  last_completed_at?: string | null;
  last_completed_latitude?: number | null;
  last_completed_longitude?: number | null;
  last_attempted_investigation_id?: number | null;
  last_attempted_at?: string | null;
  last_attempted_latitude?: number | null;
  last_attempted_longitude?: number | null;
};
export type AgentWorkProfile = {
  id?: number;
  agent_id?: number;
  depot_latitude: number | null;
  depot_longitude: number | null;
  depot_label: string | null;
  depot_source: "manual" | "nominatim" | null;
  depot_provider_ref: string | null;
  end_latitude: number | null;
  end_longitude: number | null;
  end_label: string | null;
  end_source: "manual" | "nominatim" | null;
  end_provider_ref: string | null;
  updated_at?: string;
};
export type WeeklyScheduleDay = {
  weekday: number;
  is_working: boolean;
  shift_start: string | null;
  shift_end: string | null;
  break_start: string | null;
  break_end: string | null;
};
export type WeeklySchedule = {
  id?: number;
  agent_id?: number;
  effective_from: string;
  effective_until?: string | null;
  enabled: boolean;
  region_code: string;
  max_visits: number;
  max_open_cases: number;
  days: WeeklyScheduleDay[];
};
export type AvailabilityDay = {
  work_date: string;
  status: "manual_override" | "scheduled" | "shift_ended" | "day_off" | "not_configured";
  source: "manual" | "recurring" | null;
  region_code: string | null;
  is_available: boolean;
  shift_starts_at: string | null;
  shift_ends_at: string | null;
  break_starts_at: string | null;
  break_ends_at: string | null;
  start_latitude: number | null;
  start_longitude: number | null;
  start_location_label: string | null;
  max_visits: number | null;
  max_open_cases: number | null;
};
export type AgentAvailability = {
  agent_id: number;
  from_date: string;
  to_date: string;
  days: AvailabilityDay[];
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
    reopen_on?: string | null;
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
    reopen_on?: string | null;
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
    planning_status:
      "pending" | "optimizing" | "assigned" | "unassigned" | "failed";
    reason: string | null;
    planning_run_id: number | null;
    assignment_source: "automatic" | "manual" | null;
    routing_status?: "pending" | "scheduled" | "unscheduled";
    routing_reason?: string | null;
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
  earliest_arrival_estimate_at?: string | null;
  planned_arrival_at?: string | null;
  estimated_service_start_at?: string | null;
  waiting_seconds?: number | null;
  planned_waiting_seconds?: number | null;
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
    latitude?: number;
    longitude?: number;
    distance_metres?: number;
    agent_id?: number;
    investigation_id?: number;
    reference_number?: string;
    deferred_investigation_id?: number;
    deferred_reference_number?: string;
    reason?: string;
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
  total_service_seconds?: number | null;
  total_waiting_seconds?: number | null;
  total_planned_waiting_seconds?: number | null;
  total_break_seconds?: number | null;
  planned_departure_at?: string | null;
  start: RoutePoint;
  end: RoutePoint | null;
};
export type AgentRoute = {
  work_date: string;
  route_revision: number | null;
  current_actionable_investigation_id: number | null;
  reason:
    | "no_shift"
    | "shift_unavailable"
    | "shift_ended"
    | "no_published_stops"
    | "route_refresh_pending"
    | "route_needs_refresh"
    | null;
  shift: AgentShift | null;
  route: PlanningRouteGeometry | null;
  completed_route_geometry?: LineStringGeometry | null;
  cancelled_investigations?: {
    id: number;
    reference_number: string;
    address_display: string;
    status: "cancelled";
    reopen_on: string;
    priority: InvestigationPriority;
    region_code: string | null;
    latitude: number | null;
    longitude: number | null;
  }[];
  revisit_requests?: RevisitRequest[];
  attempt_history?: RouteAttempt[];
  deferred_attempts?: RouteAttempt[];
  priority_order_warnings?: {
    type: string;
    agent_id?: number;
    investigation_id: number | null;
    reference_number: string | null;
    deferred_investigation_id: number | null;
    deferred_reference_number: string | null;
    reason: "schedule_constraint" | "search_limit" | "assignment_time_constraint";
  }[];
  stops: {
    service_duration_seconds: number;
    investigation_id: number;
    reference_number: string;
    address_display: string;
    sequence: number | null;
    estimated_arrival_at: string | null;
    earliest_arrival_estimate_at?: string | null;
    planned_arrival_at?: string | null;
    estimated_service_start_at?: string | null;
    waiting_seconds?: number | null;
    planned_waiting_seconds?: number | null;
    travel_seconds: number | null;
    travel_metres: number | null;
    latitude: number;
    longitude: number;
    priority: InvestigationPriority;
    status: InvestigationStatus;
    sequence_state: "current" | "upcoming" | "deferred" | "deferred_retry" | "handled";
    actionable: boolean;
    can_start: boolean;
    can_report: boolean;
    active_attempt_id: number | null;
    can_finalize_no_contact: boolean;
    priority_order_exception_reason: string | null;
    attempt_history: RouteAttempt[];
  }[];
};
export type RouteAttempt = {
  id: number;
  investigation_id: number;
  reference_number?: string | null;
  address_display?: string | null;
  priority?: InvestigationPriority | null;
  agent_id: number;
  work_date: string;
  planning_run_id: number | null;
  parent_event_id: number | null;
  event_type: "no_contact" | "shift_end_not_visited";
  state: "deferred" | "retrying" | "retry_failed" | "carried_over" | "resolved";
  retry_number: number;
  reason: string;
  notes: string | null;
  contact_available_from: string | null;
  contact_available_until: string | null;
  attempted_at: string;
  next_work_date: string | null;
  finalized_at: string | null;
  can_finalize_no_contact?: boolean;
  retry_actionable?: boolean;
};
export type RevisitRequest = {
  id: number;
  investigation_id: number;
  reference_number?: string | null;
  report_id: number;
  agent_id: number;
  target_work_date: string | null;
  status: "waiting_for_shift" | "queued" | "routed" | "completed" | "cancelled";
  planning_run_id: number | null;
  created_at: string;
  completed_at: string | null;
};
export type RevisitRequestState = {
  request: RevisitRequest | null;
  can_request: boolean;
};
export type InvestigationActivityItem = {
  id: number;
  label: string;
  actor_name: string | null;
  created_at: string;
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
    | "needs_refresh"
    | "unscheduled";
  refresh_errors: string[];
  planning_warnings?: {
    investigation_id: number;
    reference_number: string;
    reason: string;
  }[];
  priority_order_warnings?: {
    investigation_id: number | null;
    reference_number: string | null;
    deferred_investigation_id: number | null;
    deferred_reference_number: string | null;
    reason: "schedule_constraint" | "search_limit" | "assignment_time_constraint";
  }[];
  refresh_investigation_id: number | null;
  run_id: number | null;
  planning_status: "idle" | "queued" | "running" | "failed";
  planning_error_code: string | null;
  planning_run_id: number | null;
  open_case_count: number;
  remaining_open_capacity: number | null;
  route: PlanningRouteGeometry | null;
  completed_route_geometry?: LineStringGeometry | null;
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
  configured_region_code?: string | null;
  configured_region_name?: string | null;
  depot_label?: string | null;
  depot_latitude?: number | null;
  depot_longitude?: number | null;
  depot_distance_metres?: number | null;
  outside_configured_region?: boolean | null;
  outside_service_radius?: boolean | null;
  schedule_enabled?: boolean;
  work_profile_set?: boolean;
  availability_day?: AvailabilityDay | null;
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
  visit_outcome: VisitOutcome | null;
  status: ReportStatus;
  submitted_at: string | null;
  updated_at: string;
};
export type NoContactReviewItem = {
  event_id: number;
  investigation_id: number;
  reference_number: string;
  subject_name: string;
  assigned_agent_name: string | null;
  priority: InvestigationPriority;
  reason: string;
  state: "deferred" | "retrying" | "retry_failed" | "carried_over";
  retry_number: number;
  attempted_at: string;
  work_date: string;
  next_work_date: string | null;
  notes: string | null;
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
export type ActivityLogDetail = {
  key: string;
  label: string;
  value: string;
  redacted: boolean;
};
export type ActivityLogItem = {
  id: number;
  actor_id: number | null;
  actor_name: string | null;
  action: string;
  object_type: string;
  object_id: number | null;
  record_label: string;
  summary: string;
  detail_fields: ActivityLogDetail[];
  created_at: string;
};
export type ActivityLogPage = PageResult<ActivityLogItem>;
export type ActivityLogActorOption = {
  id: number | null;
  name: string;
};
export type ActivityLogFilterOptions = {
  actions: string[];
  object_types: string[];
  actors: ActivityLogActorOption[];
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
  status: "queued" | "running" | "published" | "failed" | "partially_published" | "unscheduled";
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
