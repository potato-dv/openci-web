import { Link } from "react-router";
import { X } from "lucide-react";
import type { PlanningRouteOverviewAgent } from "@/types/api";
import type { MapInvestigation, MapSelection } from "@/components/map/mapTypes";
import { Button, EmptyState, InlineAlert } from "@/components/ui/Primitives";
import { distance, duration, plannedWait, time, timeAfter } from "@/utils/format";
import { routeRefreshErrorCopy } from "@/utils/routeRefresh";
import {
  planningReasonCopy,
  routePlanningWarningCopy,
  planningStatusLabel,
  routeStatusLabel,
} from "./publishedRouteData";

type Props = {
  agents: PlanningRouteOverviewAgent[];
  investigations: MapInvestigation[];
  unlocatedInvestigations: {
    id: number;
    reference_number: string;
    status: string;
    region_code: string | null;
  }[];
  selection: MapSelection;
  date: string;
  scopeLabel: string;
  routesVisible: boolean;
  loading: boolean;
  retryingAgentId: number | null;
  onRetry: (agent: PlanningRouteOverviewAgent) => void;
  retryingPlanningId: number | null;
  onRetryPlanning: (item: MapInvestigation) => void;
  onSelect: (selection: MapSelection) => void;
};

const investigationFactClasses = {
  row: "grid grid-cols-[minmax(7rem,0.9fr)_minmax(0,1.1fr)] items-baseline gap-x-3",
  label: "min-w-0 text-xs leading-snug text-openci-text-muted",
  value: "m-0 min-w-0 break-words text-xs font-medium leading-snug",
};

export function PublishedRoutePanel({
  agents,
  investigations,
  unlocatedInvestigations,
  selection,
  date,
  scopeLabel,
  routesVisible,
  loading,
  retryingAgentId,
  onRetry,
  retryingPlanningId,
  onRetryPlanning,
  onSelect,
}: Props) {
  const selectedCase =
    selection?.type === "investigation"
      ? investigations.find((item) => item.id === selection.id)
      : null;
  const selectedUnlocated =
    selection?.type === "investigation"
      ? unlocatedInvestigations.find((item) => item.id === selection.id)
      : null;
  const agentId =
    selection?.type === "agent"
      ? selection.id
      : selection?.type === "investigation"
        ? selectedCase?.agent_id
        : undefined;
  const agent = agents.find((item) => item.id === agentId);
  const selectedStop = agent?.stops.find(
    (item) => item.investigation_id === selectedCase?.id,
  );
  const route = agent?.route;
  const shift = agent?.shift;
  const routeOrigin =
    route?.start ??
    (shift?.last_completed_latitude != null &&
    shift.last_completed_longitude != null
      ? { label: "Latest completed visit (estimated)" }
      : shift
        ? {
            label:
              shift.start_location_label ??
              `${shift.start_latitude.toFixed(5)}, ${shift.start_longitude.toFixed(5)}`,
          }
        : null);
  const serviceSeconds =
    agent?.stops.reduce(
      (sum, stop) => sum + stop.service_duration_seconds,
      0,
    ) ?? 0;
  const publishedRouteCount = agents.filter(
    (item) =>
      ["published", "partially_published"].includes(item.route_status) &&
      item.route?.geometry_status === "ready" &&
      item.route.geometry,
  ).length;
  const blockedAssignmentCount = agents.reduce(
    (count, item) => count + (item.planning_warnings?.length ?? 0),
    0,
  );
  const planningWarnings = agent?.planning_warnings ?? [];
  const priorityOrderWarnings = agent?.priority_order_warnings ?? [];

  return (
    <div className="planning-route-detail published-route-detail">
      <div className="route-detail-heading flex items-start justify-between gap-3 border-b border-openci-border px-4 py-3 min-[1440px]:pr-14!">
        <div className="min-w-0 flex-1">
          <h2 className="mb-1! text-sm! font-semibold! leading-tight!">
            {selectedCase
              ? "Investigation details"
              : selectedUnlocated
                ? "Location needs confirmation"
                : "Route details"}
          </h2>
          <span className="block text-xs leading-relaxed text-openci-text-muted">
            Routes refresh automatically after an assignment is saved.
          </span>
        </div>
        {selection && (
          <Button
            variant="secondary"
            className="h-8! min-h-8! shrink-0 gap-1.5! px-2! py-1! text-xs!"
            aria-label="Clear selection"
            title="Clear selection"
            onClick={() => onSelect(null)}
          >
            <X size={14} aria-hidden="true" />
            <span>Clear selection</span>
          </Button>
        )}
      </div>
      {selectedUnlocated && (
        <section className="marker-detail unlocated-detail">
          <h3>{selectedUnlocated.reference_number}</h3>
          <p>
            {selectedUnlocated.status.replaceAll("_", " ")} ·{" "}
            {selectedUnlocated.region_code ?? "Region not set"}
          </p>
          <p className="form-hint">
            This location is not confirmed, so it cannot be placed on the map or
            included in a route.
          </p>
          <Link to={`/investigations/${selectedUnlocated.id}#location`}>
            Review location
          </Link>
        </section>
      )}
      {selectedCase && (
        <div className="marker-detail">
          <h3>{selectedCase.reference_number}</h3>
          <p>{selectedCase.address_display}</p>
          <dl className="planning-investigation-facts grid gap-y-2">
            <div className={investigationFactClasses.row}>
              <dt className={investigationFactClasses.label}>
                Confirmed coordinates
              </dt>
              <dd className={investigationFactClasses.value}>
                {selectedCase.latitude.toFixed(5)},{" "}
                {selectedCase.longitude.toFixed(5)}
              </dd>
            </div>
            <div className={investigationFactClasses.row}>
              <dt className={investigationFactClasses.label}>Priority</dt>
              <dd className={investigationFactClasses.value}>
                {selectedCase.priority}
              </dd>
            </div>
            <div className={investigationFactClasses.row}>
              <dt className={investigationFactClasses.label}>
                Service duration
              </dt>
              <dd className={investigationFactClasses.value}>
                {duration(selectedCase.service_duration_seconds ?? 2700)}
              </dd>
            </div>
            {(selectedCase.visit_not_before_at ||
              selectedCase.visit_due_at) && (
              <div className={investigationFactClasses.row}>
                <dt className={investigationFactClasses.label}>Visit window</dt>
                <dd className={investigationFactClasses.value}>
                  {selectedCase.visit_not_before_at
                    ? time(selectedCase.visit_not_before_at)
                    : "Any time"}
                  {selectedCase.visit_due_at
                    ? `–${time(selectedCase.visit_due_at)}`
                    : "–Shift end"}
                </dd>
              </div>
            )}
            <div className={investigationFactClasses.row}>
              <dt className={investigationFactClasses.label}>
                Investigation status
              </dt>
              <dd className={investigationFactClasses.value}>
                {selectedCase.status.replaceAll("_", " ")}
              </dd>
            </div>
            <div className={investigationFactClasses.row}>
              <dt className={investigationFactClasses.label}>
                Automatic planning
              </dt>
              <dd className={investigationFactClasses.value}>
                {planningStatusLabel(selectedCase.planning_status ?? "pending")}
              </dd>
            </div>
            {selectedCase.agent_name && (
              <div className={investigationFactClasses.row}>
                <dt className={investigationFactClasses.label}>Assignment</dt>
                <dd className={investigationFactClasses.value}>
                  {selectedCase.assignment_source === "manual"
                    ? "Manual override"
                    : "Automatic"}{" "}
                  · {selectedCase.agent_name}
                </dd>
              </div>
            )}
            {selectedStop?.estimated_service_start_at && (
              <div className={investigationFactClasses.row}>
                <dt className={investigationFactClasses.label}>
                  Service starts
                </dt>
                <dd className={investigationFactClasses.value}>
                  {time(selectedStop.estimated_service_start_at)}
                </dd>
              </div>
            )}
          </dl>
          {selectedCase.planning_reason && (
            <p className="planning-reason-detail mt-3 rounded-md border border-openci-border bg-openci-surface-muted px-3 py-2 text-xs leading-relaxed text-openci-text-muted">
              {planningReasonCopy(selectedCase.planning_reason)}
            </p>
          )}
          {!selectedCase.agent_name && (
            <p className="planning-current-assignment">
              No official assignment has been saved.
            </p>
          )}
          <Link to={`/investigations/${selectedCase.id}`}>
            View investigation details
          </Link>
          {selectedCase.planning_status === "failed" && (
            <Button
              disabled={retryingPlanningId === selectedCase.id}
              onClick={() => onRetryPlanning(selectedCase)}
            >
              {retryingPlanningId === selectedCase.id
                ? "Retrying planning…"
                : "Retry automatic planning"}
            </Button>
          )}
        </div>
      )}
      {!selection ? (
        <section
          className="planning-route-scope-summary"
          aria-label="Route scope summary"
        >
          <h3>Published routes</h3>
          <p className="planning-route-scope-count">
            {publishedRouteCount}{" "}
            {publishedRouteCount === 1 ? "route" : "routes"} · {scopeLabel}
          </p>
          <p>
            {routesVisible
              ? "All published routes are shown. Select an agent to inspect its route and ordered stops."
              : "Routes are hidden. Agent and investigation markers remain on the map."}
          </p>
          {!loading && publishedRouteCount === 0 && (
            <p className="planning-route-scope-empty" role="status">
              No published routes are available for {date} in this scope. The
              map still shows available planning locations.
            </p>
          )}
          {!loading && blockedAssignmentCount > 0 && (
            <InlineAlert variant="warning">
              {blockedAssignmentCount} assigned{" "}
              {blockedAssignmentCount === 1
                ? "investigation is"
                : "investigations are"}{" "}
              excluded from routes. Select an affected agent to review the
              reason.
            </InlineAlert>
          )}
          {loading && (
            <p className="planning-route-scope-empty" role="status">
              Loading published routes…
            </p>
          )}
        </section>
      ) : !agent && !selectedUnlocated ? (
        <EmptyState
          title={
            selectedCase
              ? "No current route for this investigation"
              : "Agent is no longer in this scope"
          }
        >
          {selectedCase
            ? selectedCase.agent_name
              ? `Assigned to ${selectedCase.agent_name}, but no current route is published for ${date}. Check the dated shift or route refresh status.`
              : selectedCase.planning_status === "optimizing"
                ? "VROOM is evaluating eligible agents and route constraints. The investigation is not assigned until the database transaction succeeds."
                : selectedCase.planning_status === "unassigned"
                  ? "No eligible feasible assignment was found. Review the reason above or update the shift and investigation constraints."
                  : "This confirmed investigation is waiting for automatic planning."
            : "Choose an agent from the current region and work date."}
        </EmptyState>
      ) : agent ? (
        <>
          <section
            className="planning-route-summary"
            aria-label="Route summary"
          >
            <div className="planning-route-agent">
              <div>
                <h3>{agent.name}</h3>
                <span>{routeStatusLabel(agent.route_status)}</span>
              </div>
              <span className="planning-route-stop-count">
                {agent.stops.length}{" "}
                {agent.stops.length === 1 ? "stop" : "stops"}
              </span>
            </div>
            <dl className="planning-route-context">
              <div>
                <dt>Shift</dt>
                <dd>
                  {shift
                    ? `${shift.is_available ? "Available" : "Unavailable"} · ${time(shift.shift_starts_at)}–${time(shift.shift_ends_at)}`
                    : "No shift for this date"}
                </dd>
              </div>
              <div>
                <dt>Route origin</dt>
                <dd>
                  {routeOrigin?.label ?? "Unavailable"}
                </dd>
              </div>
              {shift && (
                <div>
                  <dt>Visit limit</dt>
                  <dd>{shift.max_visits} visits</dd>
                </div>
              )}
              <div>
                <dt>Open workload</dt>
                <dd>
                  {agent.open_case_count} ·{" "}
                  {agent.remaining_open_capacity ?? "—"} capacity remaining
                </dd>
              </div>
              {shift && (
                <div>
                  <dt>Shift capacity</dt>
                  <dd>{shift.max_open_cases} open cases</dd>
                </div>
              )}
            </dl>
            {route && (
              <dl className="route-metrics">
                <div>
                  <dt>Assigned stops</dt>
                  <dd>{agent.stops.length}</dd>
                </div>
              <div>
                <dt>Planned departure</dt>
                <dd>
                  {route.planned_departure_at
                    ? time(route.planned_departure_at)
                    : "Not available"}
                </dd>
              </div>
                <div>
                  <dt>Driving time</dt>
                  <dd>{duration(route.total_travel_seconds)}</dd>
                </div>
                <div>
                  <dt>Road distance</dt>
                  <dd>{distance(route.total_distance_metres)}</dd>
                </div>
                <div>
                  <dt>Investigation service time</dt>
                  <dd>{duration(route.total_service_seconds ?? serviceSeconds)}</dd>
                </div>
                <div>
                <dt>Wait at stops</dt>
                <dd>{plannedWait(route.total_planned_waiting_seconds)}</dd>
                </div>
                <div>
                  <dt>Scheduled break</dt>
                  <dd>{duration(route.total_break_seconds)}</dd>
                </div>
              </dl>
            )}
            {route?.geometry_status === "ready" && route.geometry && (
              <p className="route-geometry-label">
                Published route · validated OSRM road geometry
              </p>
            )}
          </section>

          {planningWarnings.length > 0 && (
            <div className="route-refresh-issue">
              <InlineAlert variant="warning">
                <div>
                  <p className="mb-2!">
                    These assigned investigations are excluded from this route:
                  </p>
                  <ul className="list-disc space-y-1 pl-5">
                    {planningWarnings.map((warning) => (
                      <li key={warning.investigation_id}>
                        <Link
                          to={`/investigations/${warning.investigation_id}`}
                        >
                          {warning.reference_number}
                        </Link>
                        {": "}
                        {routePlanningWarningCopy(warning.reason)}
                      </li>
                    ))}
                  </ul>
                </div>
              </InlineAlert>
            </div>
          )}

          {priorityOrderWarnings.length > 0 && (
            <div className="route-refresh-issue">
              <InlineAlert variant="warning">
                <div>
                  <p className="mb-2!">Priority sequencing needs review:</p>
                  <ul className="list-disc space-y-1 pl-5">
                    {priorityOrderWarnings.map((warning) => (
                      <li
                        key={`${warning.investigation_id ?? "route"}-${warning.deferred_investigation_id ?? "priority"}`}
                      >
                        {warning.reason === "search_limit" ? (
                          "The bounded priority optimization could not confirm a fully prioritized order. This feasible route is kept; review its stop order."
                        ) : warning.reason === "assignment_time_constraint" ? (
                          <>
                            {warning.investigation_id != null && warning.reference_number ? (
                              <Link to={`/investigations/${warning.investigation_id}`}>{warning.reference_number}</Link>
                            ) : "An earlier assignment"}
                            {" with the same priority stays first because visit windows, shift hours, or a break prevent the assignment-time order."}
                          </>
                        ) : (
                          <>
                            {warning.investigation_id != null &&
                            warning.reference_number ? (
                              <Link
                                to={`/investigations/${warning.investigation_id}`}
                              >
                                {warning.reference_number}
                              </Link>
                            ) : (
                              "A lower-priority stop"
                            )}
                            {" is scheduled before higher priority "}
                            {warning.deferred_investigation_id != null &&
                            warning.deferred_reference_number ? (
                              <Link
                                to={`/investigations/${warning.deferred_investigation_id}`}
                              >
                                {warning.deferred_reference_number}
                              </Link>
                            ) : (
                              "work"
                            )}
                            {". Visit windows, shift hours, or a break require this order."}
                          </>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              </InlineAlert>
            </div>
          )}

          {(agent.route_status === "failed" ||
            agent.route_status === "partially_published") && (
            <div className="route-refresh-issue">
              {agent.refresh_errors.length > 0 && (
                <InlineAlert variant="warning">
                  {[
                    ...new Set(agent.refresh_errors.map(routeRefreshErrorCopy)),
                  ].join(" ")}
                </InlineAlert>
              )}
              {agent.refresh_errors.length === 0 &&
                planningWarnings.length === 0 && (
                  <InlineAlert variant="warning">
                    The assignment is saved, but a current route could not be
                    published. Review the shift and investigation locations,
                    then retry.
                  </InlineAlert>
                )}
              {(agent.route_status === "failed" ||
                agent.route_status === "partially_published") &&
                agent.refresh_investigation_id &&
                agent.refresh_errors.length > 0 && (
                  <Button
                    disabled={retryingAgentId === agent.id}
                    onClick={() => onRetry(agent)}
                  >
                    {retryingAgentId === agent.id
                      ? "Retrying route…"
                      : "Retry route update"}
                  </Button>
                )}
            </div>
          )}
          {(agent.route_status === "queued" ||
            agent.route_status === "running") && (
            <div className="route-refresh-progress" role="status">
              <strong>
                {agent.route_status === "queued"
                  ? "Route update queued · not published"
                  : "Building route · not published"}
              </strong>
              <span>
                The updated route will appear here only after OSRM geometry is
                validated.
              </span>
            </div>
          )}
          {(!shift || !shift.is_available) && (
            <InlineAlert variant="warning">
              {shift
                ? "This shift is unavailable, so there is no route to publish. Update the shift before retrying."
                : "An available shift for this date is required before assigned work can be routed."}{" "}
              <Link to={`/field-agents?date=${date}`}>Manage shifts</Link>
            </InlineAlert>
          )}
          {selectedCase && selectedStop && (
            <div className="marker-detail selected-stop-detail">
              <h3>{selectedCase.reference_number}</h3>
              <p>{selectedCase.address_display}</p>
              <p>
                Stop {selectedStop.sequence ?? "—"} · {selectedCase.priority}{" "}
                priority
              </p>
              <Link to={`/investigations/${selectedCase.id}`}>
                View investigation details
              </Link>
            </div>
          )}
          <div className="planning-stop-heading">
            <h3>Stop sequence</h3>
            <span>{agent.stops.length} assigned</span>
          </div>
          {agent.stops.length ? (
            <ol className="ordered-stops">
              {agent.stops.map((stop) => (
                <li
                  key={stop.investigation_id}
                  className={
                    selectedCase?.id === stop.investigation_id ? "selected" : ""
                  }
                >
                  <Button
                    className="stop-selection planning-stop-selection"
                    aria-pressed={selectedCase?.id === stop.investigation_id}
                    onClick={() =>
                      onSelect({
                        type: "investigation",
                        id: stop.investigation_id,
                      })
                    }
                  >
                    <span className="stop-number">{stop.sequence ?? "—"}</span>
                    <span className="planning-stop-content">
                      <span className="planning-stop-title">
                        <strong>{stop.reference_number}</strong>
                        {selectedCase?.id === stop.investigation_id && (
                          <span className="planning-stop-current">
                            Selected
                          </span>
                        )}
                      </span>
                      <small>{stop.address_display}</small>
                      <span className="planning-stop-metrics">
                        <span>
                          <small>
                            Earliest arrival estimate · depart as soon as possible
                          </small>
                          <strong>
                            {time(
                              stop.earliest_arrival_estimate_at ??
                                stop.estimated_arrival_at,
                            )}
                          </strong>
                        </span>
                        <span>
                          <small>Planned arrival</small>
                          <strong>
                            {stop.planned_arrival_at
                              ? time(stop.planned_arrival_at)
                              : "Not available"}
                          </strong>
                        </span>
                        <span>
                          <small>Wait at stop</small>
                          <strong>{plannedWait(stop.planned_waiting_seconds)}</strong>
                        </span>
                        <span>
                          <small>Service starts</small>
                          <strong>
                            {stop.estimated_service_start_at
                              ? time(stop.estimated_service_start_at)
                              : "Not available"}
                          </strong>
                        </span>
                        <span>
                          <small>Service ends</small>
                          <strong>
                            {timeAfter(
                              stop.estimated_service_start_at,
                              stop.service_duration_seconds,
                            )}
                          </strong>
                        </span>
                        <span>
                          <small>From previous stop</small>
                          <strong>
                            {duration(stop.travel_seconds)} ·{" "}
                            {distance(stop.travel_metres)}
                          </strong>
                        </span>
                      </span>
                    </span>
                  </Button>
                </li>
              ))}
            </ol>
          ) : (
            <p className="planning-no-stops">
              {agent.route_status === "queued" ||
              agent.route_status === "running"
                ? "Stops will appear when the automatic route refresh completes."
                : agent.route_status === "failed" ||
                    agent.route_status === "partially_published"
                  ? "No current route was published. Resolve the issue above and retry."
                  : agent.route_status === "needs_refresh"
                    ? "Assigned investigations exist, but no route matching the current assignments is published. Reassign or retry the latest failed refresh from the investigation."
                    : "No route-eligible investigations are assigned to this agent for the selected date."}
            </p>
          )}
          {route?.geometry_status === "failed" && (
            <InlineAlert variant="warning">
              Road geometry is unavailable or invalid. No straight-line fallback
              is shown.
            </InlineAlert>
          )}
        </>
      ) : null}
    </div>
  );
}
