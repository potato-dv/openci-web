import type { PlanningDashboard, PlanningMapData, PlanningRouteOverview } from "@/types/api";
import { time } from "@/utils/format";
import type { MapAgent, MapInvestigation, MapRoute } from "@/components/map/mapTypes";

export function routeStatusLabel(status: PlanningRouteOverview["agents"][number]["route_status"]) {
  const labels = {
    none: "No route published",
    queued: "Route update queued",
    running: "Building route",
    published: "Route published",
    failed: "Route update failed",
    partially_published: "Some routes need attention",
    needs_refresh: "Route needs an update",
  };
  return labels[status];
}

export function planningStatusLabel(status: NonNullable<MapInvestigation["planning_status"]>) {
  const labels = {
    pending: "Pending",
    optimizing: "Optimizing",
    assigned: "Assigned",
    unassigned: "Unassigned",
    failed: "Planning failed",
  };
  return labels[status];
}

export function planningReasonCopy(reason: string | null | undefined) {
  if (!reason) return "";
  const copy: Record<string, string> = {
    location_unconfirmed: "Confirm this location before planning can start.",
    no_available_agents: "No active agent has an available shift for this date.",
    agent_open_case_limit: "Available agents have reached their open case capacity.",
    no_feasible_route_under_constraints: "No feasible route fits the shifts, travel times, service times, time windows, and capacity limits.",
    deadline_before_service_window: "The requested visit window is shorter than the investigation service duration.",
    no_routable_agent_start: "No eligible agent starting point connects to the road network.",
    road_snap_too_far: "The confirmed location is too far from a routable road.",
    no_road_connected_agent: "No available agent can reach this investigation through the configured road network.",
    planning_scope_capacity_exceeded: "This planning batch exceeds the route planner capacity; reduce the scope or shift workload, then retry.",
    queue_unavailable: "The background planning worker could not accept this run.",
    route_geometry_incomplete: "The route geometry did not validate, so no new assignments were published.",
    auto_route_incomplete: "The optimizer returned an incomplete result, so no assignments were published.",
  };
  return copy[reason] ?? reason.replaceAll("_", " ");
}

export function buildPublishedRouteMapData(
  inventory: PlanningMapData | null | undefined,
  overview: PlanningRouteOverview | null | undefined,
  regionLabels: Map<string, string>,
  dashboard?: PlanningDashboard | null,
) {
  const overviewByAgent = new Map(
    overview?.agents.map((agent) => [agent.id, agent]) ?? [],
  );
  const stopByCase = new Map(
    overview?.agents.flatMap((agent) =>
      agent.stops.map((stop) => [stop.investigation_id, { ...stop, agent_id: agent.id, agent_name: agent.name }] as const),
    ) ?? [],
  );
  const stateByCase = new Map(
    dashboard?.investigation_states.map((item) => [item.investigation_id, item]) ?? [],
  );
  const agents: MapAgent[] = (inventory?.agents ?? []).flatMap((agent) => {
    if (!agent.start) return [];
    const routeAgent = overviewByAgent.get(agent.id);
    const regionLabel = agent.region_code
      ? regionLabels.get(agent.region_code)
      : undefined;
    return [{
      id: agent.id,
      name: agent.name,
      start: agent.start,
      region_code: agent.region_code,
      region_label: regionLabel,
      is_active: agent.is_active,
      is_available: agent.is_available,
      route_status: routeAgent?.route_status ?? "none",
      shift_label: agent.is_available === null
        ? "No shift for this date"
        : `${agent.is_available ? "Available" : "Unavailable"} · ${time(agent.shift_starts_at)}–${time(agent.shift_ends_at)}`,
    }];
  });
  const investigations: MapInvestigation[] = (inventory?.investigations ?? []).map((item) => {
    const stop = stopByCase.get(item.id);
    const state = stateByCase.get(item.id);
    return {
      id: item.id,
      reference_number: item.reference_number,
      address_display: item.address_display,
      latitude: item.latitude,
      longitude: item.longitude,
      priority: item.priority,
      status: item.status,
      region_code: item.region_code,
      region_label: item.region_code ? regionLabels.get(item.region_code) : undefined,
      agent_id: item.assigned_agent_id ?? stop?.agent_id ?? null,
      agent_name: stop?.agent_name ?? item.assigned_agent_name ?? null,
      sequence: stop?.sequence ?? null,
      outcome: item.assigned_agent_id ? "assigned" : "unassigned",
      service_duration_seconds: item.service_duration_seconds,
      planning_status: state?.planning_status ?? (item.assigned_agent_id ? "assigned" : "pending"),
      planning_reason: state?.reason ?? null,
      assignment_source: state?.assignment_source ?? null,
      estimated_arrival_at: stop?.estimated_arrival_at ?? null,
      visit_not_before_at: item.visit_not_before_at,
      visit_due_at: item.visit_due_at,
    };
  });
  const routes: MapRoute[] = (overview?.agents ?? []).flatMap((agent) =>
    agent.route?.geometry_status === "ready" && agent.route.geometry
      ? [{ agent_id: agent.id, agent_name: agent.name, geometry: agent.route.geometry }]
      : [],
  );
  return { agents, investigations, routes };
}
