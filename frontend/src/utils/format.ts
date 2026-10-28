export function manilaToday() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Manila",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}
export function time(value: string | null | undefined) {
  return value
    ? new Intl.DateTimeFormat("en-PH", {
        timeZone: "Asia/Manila",
        hour: "numeric",
        minute: "2-digit",
      }).format(new Date(value))
    : "—";
}
export function date(value: string | null | undefined) {
  return value
    ? new Intl.DateTimeFormat("en-PH", {
        timeZone: "Asia/Manila",
        month: "short",
        day: "numeric",
        year: "numeric",
      }).format(new Date(value))
    : "—";
}
export function distance(value: number | null | undefined) {
  return value == null ? "Unavailable" : `${(value / 1000).toFixed(1)} km`;
}
export function duration(value: number | null | undefined) {
  if (value == null) return "Unavailable";
  const minutes = Math.round(value / 60);
  return minutes >= 60
    ? `${Math.floor(minutes / 60)}h ${minutes % 60}m`
    : `${minutes} min`;
}
export function friendlyError(value: string) {
  const messages: Record<string, string> = {
    route_geometry_incomplete:
      "Road geometry is incomplete, so the automatic route could not be published. Check routing service health and retry planning.",
    stale_plan:
      "The planning inputs changed while this route was being calculated. The system will plan again from the current data.",
    planning_run_not_ready:
      "This automatic planning run is no longer current. Reload the dashboard for its latest status.",
    run_too_large:
      "Select no more than 80 unique investigation and depot locations combined.",
    locked_agent_not_selected:
      "An existing assignment belongs to an agent outside this selection. Include that agent or adjust the investigation selection.",
    geocoder_unavailable:
      "Address search is unavailable. Try again or select and confirm a point manually.",
    queue_unavailable:
      "The optimization queue is unavailable. Try again when the planning worker is running.",
    planning_dependencies_unavailable:
      "Route planning is temporarily unavailable. Review the routing-service status, then retry the checks.",
    dataset_unconfigured:
      "The Philippines road dataset is not configured. Prepare the OSRM graph and set its dataset version.",
    worker_unavailable:
      "The optimization worker is unavailable. Start the worker, then retry the checks.",
    osrm_unavailable:
      "The OSRM road router is unavailable. Start OSRM with the prepared Philippines dataset, then retry.",
    vroom_unavailable:
      "The VROOM optimizer is unavailable. Start VROOM after OSRM is healthy, then retry.",
    osrm_snap_failed:
      "Locations could not be matched to the road network because OSRM is unavailable. Restore the route engine and retry automatic planning.",
    osrm_snap_shape_invalid:
      "OSRM returned invalid road matches. Verify the Philippines graph, restart OSRM, and retry automatic planning.",
    osrm_table_unavailable:
      "Travel times could not be calculated because OSRM is unavailable. Restore the route engine and retry automatic planning.",
    osrm_table_failed:
      "OSRM could not calculate the requested travel matrix. Verify the graph and confirmed locations, then retry automatic planning.",
    osrm_matrix_shape_invalid:
      "OSRM returned an invalid travel matrix. Verify the graph, restart OSRM, and retry automatic planning.",
    vroom_solver_failed:
      "The optimizer could not produce a valid route. Review agent shifts and investigation details, then retry planning.",
    planning_disabled:
      "Route planning is disabled for this deployment.",
    osrm_route_unavailable:
      "Road geometry could not be loaded. Retry automatic planning when the routing service is available.",
    osrm_route_failed:
      "OSRM could not build a road route for the ordered stops. Review their confirmed locations and retry automatic planning.",
    osrm_route_shape_invalid:
      "OSRM returned invalid road geometry. Verify the graph, restart OSRM, and retry automatic planning.",
    route_geometry_invalid:
      "Saved road geometry is invalid, so the route was not published. Check routing service health and retry planning.",
    optimization_failed:
      "Optimization failed unexpectedly. Retry once, then review the worker logs if it happens again.",
    inputs_changed:
      "Investigations or shifts changed while this route was being calculated. The system will plan again from current data.",
    shift_changed:
      "An agent shift changed while planning. The system will recalculate from current shift details.",
    investigation_changed:
      "An investigation changed while planning. The system will recalculate from current details.",
    no_eligible_agents:
      "No selected agent has an active, available shift with a confirmed starting point for this scope.",
    no_eligible_investigations:
      "None of the selected investigations is still assignable. Reload readiness and update the selection.",
    no_feasible_visit_windows:
      "The selected investigations cannot fit within the available shift and visit windows.",
    agent_start_off_road:
      "Agent starting points are too far from routable roads. Correct the shifts and retry automatic planning.",
    assignment_lock_conflict:
      "An existing assignment changed during planning. Reload readiness before regenerating.",
    locked_case_not_feasible:
      "An existing assignment cannot fit the selected shift constraints. Adjust that shift or selection.",
    route_refresh_pending:
      "Your assignments are saved. The route is being refreshed and will appear when it is ready.",
    route_needs_refresh:
      "Your assignments are saved, but there is no current route. Ask a supervisor to retry automatic planning.",
  };
  return messages[value] ?? value.replaceAll("_", " ");
}
