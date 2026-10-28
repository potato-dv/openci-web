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
  visit_not_before_at?: string | null;
  visit_due_at?: string | null;
};
export type MapRoute = {
  agent_id: number;
  agent_name: string;
  geometry: LineStringGeometry | null;
};
export type MapSelection = {
  type: "agent" | "investigation";
  id: number;
} | null;
export const routeColors = [
  "#4658b9",
  "#087e8b",
  "#a05221",
  "#8e4e99",
  "#3c7b3a",
  "#a33e58",
];
export function routeColor(index: number) {
  return routeColors[index % routeColors.length];
}
export function leafletPositions(
  geometry: LineStringGeometry,
): [number, number][] {
  return geometry.coordinates.map(([longitude, latitude]) => [
    latitude,
    longitude,
  ]);
}
