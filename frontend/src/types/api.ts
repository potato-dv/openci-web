export type UserRole = "admin" | "supervisor" | "agent";

export type InvestigationStatus =
  | "pending"
  | "assigned"
  | "in_progress"
  | "under_review"
  | "returned_for_correction"
  | "completed";

export type InvestigationPriority = "normal" | "high" | "urgent";
export type ReportStatus = "draft" | "submitted";
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
  subject_name: string;
  address: string;
  status: InvestigationStatus;
  priority: InvestigationPriority;
  assigned_agent_id?: number | null;
  created_at?: string;
};

export type NewInvestigation = {
  reference_number: string;
  subject_name: string;
  address: string;
  priority: InvestigationPriority;
};

export type Assignment = {
  id: number;
  investigation_id: number;
  agent_id: number;
  assigned_by_id: number;
  note: string | null;
  is_active: boolean;
  assigned_at: string;
  unassigned_at: string | null;
};

export type Report = {
  id: number;
  investigation_id: number;
  author_id: number;
  content: string;
  status: ReportStatus;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
};

export type Review = {
  id: number;
  investigation_id: number;
  report_id: number;
  reviewer_id: number;
  decision: ReviewDecision;
  comments: string | null;
  reviewed_at: string;
};

export type LoginResponse = {
  access_token: string;
  token_type: "bearer";
};
