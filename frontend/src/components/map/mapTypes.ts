import type {
  InvestigationPriority,
  InvestigationStatus,
  LineStringGeometry,
  RoutePoint,
} from "../../types/api";
export type MapAgent = {
  region_label?: string;
  region_code?: string | null;
  shift_label?: string;
  id: number;
  name: string;
  start: RoutePoint;
  depot?: RoutePoint | null;
  is_active?: boolean;
  is_available?: boolean | null;
  route_status?:
    | "none"
    | "queued"
    | "running"
    | "published"
    | "failed"
    | "partially_published"
    | "needs_refresh";
  included?: boolean;
  number?: number;
};
export type MapInvestigation = {
  id: number;
  reference_number: string;
  address_display: string;
  latitude: number;
  longitude: number;
  priority: InvestigationPriority;
  status: InvestigationStatus;
  reopen_on?: string | null;
  region_code?: string | null;
  region_label?: string;
  sequence?: number | null;
  agent_id?: number | null;
  agent_name?: string | null;
  included?: boolean;
  outcome?: "assigned" | "unassigned";
  service_duration_seconds?: number;
  planning_status?: "pending" | "optimizing" | "assigned" | "unassigned" | "failed";
  planning_reason?: string | null;
  assignment_source?: "automatic" | "manual" | null;
  estimated_arrival_at?: string | null;
  planned_arrival_at?: string | null;
  estimated_service_start_at?: string | null;
  visit_not_before_at?: string | null;
  visit_due_at?: string | null;
};
export type MapRoute = {
  agent_id: number;
  agent_name: string;
  geometry: LineStringGeometry | null;
  completed_geometry?: LineStringGeometry | null;
};
export type MapSelection = {
  type: "agent" | "investigation";
  id: number;
} | null;
export const ROUTE_BLUE = "#4285f4";
export const ESTIMATED_TRAVELED_GRAY = "#64748b";
export const ESTIMATED_TRAVELED_OPACITY = 0.58;
export type RouteLineStyle = {
  color: string;
  dashArray?: string;
};

export function routeColor(_agentId: number) {
  return ROUTE_BLUE;
}

export function investigationPriorityColor(priority: InvestigationPriority) {
  return {
    normal: "#15803d",
    high: "#eab308",
    urgent: "#dc2626",
  }[priority];
}

export function routeLineStyles(routes: readonly MapRoute[]) {
  return new Map(
    routes.map((route) => [route.agent_id, { color: ROUTE_BLUE }]),
  );
}
export function leafletPositions(
  geometry: LineStringGeometry,
): [number, number][] {
  return geometry.coordinates.map(([longitude, latitude]) => [
    latitude,
    longitude,
  ]);
}
