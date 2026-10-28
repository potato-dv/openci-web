import type {
  AgentRoute,
  PlanningMapData,
  PlanningDashboard,
  PlanningReadiness,
  PlanningRouteOverview,
  PlanningRun,
  PlanningServiceStatus,
} from "@/types/api";
import { requestJson } from "@/services/http";

export function getPlanningReadiness(
  token: string,
  workDate: string,
  regionCode: string,
  resolution: 7 | 8 | 9,
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({
    work_date: workDate,
    region_code: regionCode,
    resolution: String(resolution),
  });
  return requestJson<PlanningReadiness>(`/planning/readiness?${params}`, {
    token,
    signal,
  });
}

export function getPlanningMapData(
  token: string,
  workDate: string,
  regionCode?: string,
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({ work_date: workDate });
  if (regionCode) params.set("region_code", regionCode);
  return requestJson<PlanningMapData>(`/planning/map-data?${params}`, {
    token,
    signal,
  });
}

export function getPlanningRouteOverview(
  token: string,
  workDate: string,
  regionCode?: string,
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({ work_date: workDate });
  if (regionCode) params.set("region_code", regionCode);
  return requestJson<PlanningRouteOverview>(
    `/planning/route-overview?${params}`,
    { token, signal },
  );
}

export function getPlanningDashboard(
  token: string,
  workDate: string,
  regionCode?: string,
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({ work_date: workDate });
  if (regionCode) params.set("region_code", regionCode);
  return requestJson<PlanningDashboard>(`/planning/dashboard?${params}`, {
    token,
    signal,
  });
}

export function retryAutomaticPlanning(
  token: string,
  investigationId: number,
  workDate: string,
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({ work_date: workDate });
  return requestJson<PlanningRun>(
    `/planning/investigations/${investigationId}/retry?${params}`,
    { method: "POST", token, signal },
  );
}

export function getPlanningServiceStatus(
  token: string,
  refresh = false,
  signal?: AbortSignal,
) {
  const params = refresh ? "?refresh=true" : "";
  return requestJson<PlanningServiceStatus>(
    `/planning/service-status${params}`,
    { token, signal },
  );
}

export function getPlanningRun(
  token: string,
  runId: number,
  signal?: AbortSignal,
) {
  return requestJson<PlanningRun>(`/planning/runs/${runId}`, { token, signal });
}

export function getAgentRoute(
  token: string,
  workDate: string,
  signal?: AbortSignal,
) {
  return requestJson<AgentRoute>(
    `/planning/my-route?work_date=${encodeURIComponent(workDate)}`,
    { token, signal },
  );
}
