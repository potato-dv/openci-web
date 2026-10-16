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
export type InvestigationOutcome = "verified" | "not_verified" | "unable_to_verify" | "inconclusive";
export type OccupancyStatus = "occupied" | "vacant" | "unknown" | "not_applicable";
export type ReportStatus = "draft" | "submitted" | "approved" | "returned_for_correction";
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
};

export type LocationOption = { code: string; name: string; type?: string };
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
  note: string | null;
  is_active: boolean;
  assigned_at: string;
  unassigned_at: string | null;
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
