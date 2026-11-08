import { useState } from "react";
import { Link } from "react-router";
import type { AgentRoute } from "@/types/api";
import { OperationsMap } from "@/components/map/OperationsMap";
import "@/styles/planning.css";
import type { MapRoute, MapSelection } from "@/components/map/mapTypes";
import { EmptyState, InlineAlert, Tabs } from "@/components/ui/Primitives";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { distance, duration, plannedWait, time, timeAfter } from "@/utils/format";
import { finalizeNoContactReport } from "@/features/reports/api";

function emptyCopy(reason: AgentRoute["reason"]) {
  if (reason === "no_shift") {
    return ["No shift configured", "A supervisor must configure a shift for this date."];
  }
  if (reason === "shift_unavailable") {
    return ["Shift unavailable", "No new investigations will be assigned while this shift is unavailable."];
  }
  if (reason === "shift_ended") {
    return [
      "No assigned investigations",
      "There are no unfinished investigations assigned to you for this shift.",
    ];
  }
  if (reason === "route_refresh_pending") {
    return [
      "Route update in progress",
      "Your last reported stop remains your estimated location while the remaining route refreshes.",
    ];
  }
  if (reason === "route_needs_refresh") {
    return [
      "Route needs an update",
      "Your assigned investigations remain listed while the system retries route planning. Stop order and travel estimates will appear when a route is published.",
    ];
  }
  return [
    "No route stops",
    "Route stops appear here after automatic planning or an authorized manual override publishes an assignment.",
  ];
}

export function AgentRouteView({
  data,
  agentId,
  agentName,
  token,
  onRefresh,
  canAct = false,
}: {
  data: AgentRoute;
  agentId: number;
  agentName: string;
  token?: string;
  onRefresh?: () => void;
  canAct?: boolean;
}) {
  const [selection, setSelection] = useState<MapSelection>(null);
  const [tab, setTab] = useState("list");
  const [busyAttemptId, setBusyAttemptId] = useState<number | null>(null);
  const [attemptError, setAttemptError] = useState("");
  const [attemptMessage, setAttemptMessage] = useState("");
  const start =
    data.route?.start ??
    (data.shift?.last_attempted_latitude != null &&
    data.shift.last_attempted_longitude != null &&
    data.shift.last_attempted_at != null &&
    (!data.shift.last_completed_at || new Date(data.shift.last_attempted_at) > new Date(data.shift.last_completed_at))
      ? {
          latitude: data.shift.last_attempted_latitude,
          longitude: data.shift.last_attempted_longitude,
          label: "Latest recorded attempt (estimated)",
        }
      : data.shift?.last_completed_latitude != null &&
    data.shift.last_completed_longitude != null
      ? {
          latitude: data.shift.last_completed_latitude,
          longitude: data.shift.last_completed_longitude,
          label: "Latest completed visit (estimated)",
        }
      : data.shift
        ? {
            latitude: data.shift.start_latitude,
            longitude: data.shift.start_longitude,
            label: data.shift.start_location_label ?? "Configured shift starting point",
          }
        : null);
  const [emptyTitle, emptyDescription] = emptyCopy(data.reason);
  const cancelledInvestigations = data.cancelled_investigations ?? [];
  const deferredAttempts = data.deferred_attempts ?? [];
  const hasMapItems = data.stops.length > 0 || cancelledInvestigations.length > 0;
  const mapRoute: MapRoute | null = data.route
    ? {
        agent_id: data.route.agent_id,
        agent_name: data.route.agent_name,
        geometry:
          data.route.geometry_status === "ready" ? data.route.geometry : null,
        completed_geometry: data.completed_route_geometry ?? null,
      }
    : data.completed_route_geometry
      ? {
          agent_id: agentId,
          agent_name: agentName,
          geometry: null,
          completed_geometry: data.completed_route_geometry,
        }
      : null;

  async function finalizeAttempt(attempt: NonNullable<AgentRoute["deferred_attempts"]>[number]) {
    if (!token || data.route_revision == null) return;
    setBusyAttemptId(attempt.id);
    setAttemptError("");
    setAttemptMessage("");
    try {
      const finalized = await finalizeNoContactReport(
        token,
        attempt.investigation_id,
        attempt.id,
        { work_date: data.work_date, route_revision: data.route_revision },
      );
      setAttemptMessage(finalized.next_work_date
        ? `${attempt.reference_number ?? "Investigation"} will continue on ${finalized.next_work_date}.`
        : `${attempt.reference_number ?? "Investigation"} was carried forward for the next available shift.`);
      onRefresh?.();
    } catch (err) {
      setAttemptError(err instanceof Error ? err.message : "Could not submit the No Contact Report.");
    } finally {
      setBusyAttemptId(null);
    }
  }

  function dateTimeLabel(value: string | null) {
    if (!value) return "Not provided";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "Not provided";
    return new Intl.DateTimeFormat("en-PH", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "Asia/Manila",
    }).format(parsed);
  }

  function reasonLabel(value: string) {
    return ({
      no_contact_person: "No contact person available",
      nobody_at_location: "Nobody at the location",
      requested_later_visit: "Contact requested a later visit",
      other: "Other",
      shift_end_not_visited: "Shift End — Not Visited",
      retry_started: "Retry started",
    } as Record<string, string>)[value] ?? value.replaceAll("_", " ");
  }

  return (
    <div className="agent-route-view">
      {(data.reason === "shift_ended" ||
        (data.reason === "shift_unavailable" && data.stops.length > 0)) && (
        <InlineAlert variant="info">
          {data.reason === "shift_ended"
            ? "Your shift has ended. You may finish these assigned investigations; new investigations will not be assigned to you for this shift."
            : "This shift is unavailable for new assignments. You may continue working on the investigations already assigned to you."}
        </InlineAlert>
      )}
      {data.stops.length ? (
        <>
          {data.current_actionable_investigation_id != null && (
            <InlineAlert variant="info">
              <strong>{data.stops.find((stop) => stop.investigation_id === data.current_actionable_investigation_id)?.can_start || data.stops.find((stop) => stop.investigation_id === data.current_actionable_investigation_id)?.can_report
                ? "Current Investigation — Proceed Here:"
                : "Next stop in sequence:"}</strong>{" "}
              {data.stops.find((stop) => stop.investigation_id === data.current_actionable_investigation_id)?.reference_number ?? "See the stop marked Current"}.
              Upcoming stops stay view-only until this stop is submitted or deferred.
            </InlineAlert>
          )}
          <dl className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7 [&>div]:rounded-lg [&>div]:border [&>div]:border-[#dfe7f1] [&>div]:bg-[#f5f8fc] [&>div]:p-3 [&_dt]:text-[11px] [&_dt]:font-medium [&_dt]:text-[#6d7f9b] [&_dd]:mb-0 [&_dd]:mt-2 [&_dd]:text-base [&_dd]:font-semibold [&_dd]:tabular-nums [&_dd]:text-[#1d3558]">
            <div>
              <dt>{data.route ? "Published stops" : "Assigned investigations"}</dt>
              <dd>{data.stops.length}</dd>
            </div>
            <div>
              <dt>Planned departure</dt>
              <dd>
                {data.route?.planned_departure_at
                  ? time(data.route.planned_departure_at)
                  : "Not available"}
              </dd>
            </div>
            <div>
              <dt>Road travel</dt>
              <dd>{data.route ? duration(data.route.total_travel_seconds) : "—"}</dd>
            </div>
            <div>
              <dt>Distance</dt>
              <dd>{data.route ? distance(data.route.total_distance_metres) : "—"}</dd>
            </div>
            <div>
              <dt>Total service</dt>
              <dd>{data.route ? duration(data.route.total_service_seconds) : "—"}</dd>
            </div>
            <div>
              <dt>Wait at stops</dt>
              <dd>{data.route ? plannedWait(data.route.total_planned_waiting_seconds) : "Not available"}</dd>
            </div>
            <div>
              <dt>Scheduled break</dt>
              <dd>{data.route ? duration(data.route.total_break_seconds) : "—"}</dd>
            </div>
          </dl>
          <p className="form-hint">
            Route origin: {start?.label ?? "Unavailable"}. Location is based on
            submitted visits, not live GPS. Estimated times use Philippine time.
          </p>
          {!data.route?.geometry && (
            data.route ? (
              <InlineAlert variant="warning">
                Road geometry is unavailable for this published route. The stop
                list is available below.
              </InlineAlert>
            ) : (
              <InlineAlert variant="warning">
                These investigations are still assigned, but this route has not
                been published. Stop order, arrival times, and map geometry will
                appear after a successful route update.
              </InlineAlert>
            )
          )}
          {data.priority_order_warnings?.length ? (
            <InlineAlert variant="warning">
              {data.priority_order_warnings.some((warning) => warning.reason === "search_limit")
                ? "The route search reached its limit. The feasible route is kept; review the displayed stop order."
                : "A visit window, shift hour, break, or retry phase requires an exception to the usual route order. The affected stop is marked below."}
            </InlineAlert>
          ) : null}
        </>
      ) : (
        <EmptyState title={cancelledInvestigations.length ? "Paused until the next workday" : emptyTitle}>
          {cancelledInvestigations.length
            ? "No visit was recorded for these investigations during the shift. They will be available again on the retry date shown below."
            : emptyDescription}
        </EmptyState>
      )}

      {cancelledInvestigations.length > 0 && (
        <section className="route-cancelled-investigations" aria-label="Paused investigations">
          <h3>Paused until the next workday</h3>
          <ul>
            {cancelledInvestigations.map((item) => (
              <li key={item.id}>
                <span>
                  <strong>{item.reference_number}</strong>
                  <span>{item.address_display}</span>
                  <StatusBadge status="cancelled" reopenOn={item.reopen_on} />
                </span>
                <Link to={`/investigations/${item.id}`}>View investigation</Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {deferredAttempts.length > 0 && (
        <section className="route-cancelled-investigations" aria-label="Deferred and carried-over investigations">
          <h3>Deferred and carried-over work</h3>
          {attemptError && <p className="error" role="alert">{attemptError}</p>}
          {attemptMessage && <p className="success-message" role="status">{attemptMessage}</p>}
          <ul>
            {deferredAttempts.map((attempt) => (
              <li key={attempt.id}>
                <span>
                  <strong>{attempt.reference_number ?? `Investigation ${attempt.investigation_id}`}</strong>
                  {attempt.priority && <span className={`priority-label priority-${attempt.priority}`}>{attempt.priority}</span>}
                  <span>{attempt.address_display}</span>
                  <span>{attempt.event_type === "shift_end_not_visited" ? "Shift End — Not Visited" : reasonLabel(attempt.reason)}</span>
                  <span>Attempted {dateTimeLabel(attempt.attempted_at)}</span>
                  {attempt.contact_available_from && (
                    <span>Contact available {dateTimeLabel(attempt.contact_available_from)}{attempt.contact_available_until ? `–${dateTimeLabel(attempt.contact_available_until)}` : " onward"}</span>
                  )}
                  <span>
                    {attempt.retry_actionable
                      ? "Same-day retry is ready"
                      : attempt.state === "retry_failed"
                        ? "Retry used · carry-over ready"
                        : attempt.state === "carried_over"
                          ? `Next work date: ${attempt.next_work_date ?? "next available shift"}`
                          : attempt.state.replaceAll("_", " ")}
                  </span>
                </span>
                <span className="flex flex-wrap items-center gap-2">
                  {canAct && attempt.can_finalize_no_contact && attempt.event_type === "no_contact" && (
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => void finalizeAttempt(attempt)}
                      disabled={busyAttemptId != null}
                    >
                      {busyAttemptId === attempt.id ? "Submitting…" : "Submit No Contact Report"}
                    </button>
                  )}
                  <Link to={`/investigations/${attempt.investigation_id}`}>View investigation</Link>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {data.revisit_requests?.length ? (
        <section className="route-revisit-requests" aria-label="Correction revisit requests">
          <h3>Correction revisits</h3>
          <ul>
            {data.revisit_requests.map((request) => (
              <li key={request.id}>
                <span>
                  <strong>{request.reference_number ?? `Investigation ${request.investigation_id}`}</strong>
                  <span>
                    {request.status === "waiting_for_shift"
                      ? request.target_work_date
                        ? `Scheduled for ${request.target_work_date}`
                        : "Waiting for your next available shift"
                      : request.status === "queued"
                        ? `Route update queued for ${request.target_work_date ?? "the selected shift"}`
                        : `Route published for ${request.target_work_date ?? "your shift"}`}
                  </span>
                </span>
                <Link to={`/investigations/${request.investigation_id}`}>
                  View concern
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {start && (
        <>
          {hasMapItems && (
            <div className="mobile-route-tabs">
              <Tabs
                label="Route view"
                value={tab}
                onChange={setTab}
                items={[
                  { value: "list", label: "Stop list" },
                  { value: "map", label: "Map" },
                ]}
              />
            </div>
          )}
          <div
            className={`route-split ${hasMapItems ? `active-${tab}` : "route-origin-only"}`}
          >
            <div className="published-route-map">
              <OperationsMap
                agents={[
                  {
                    id: agentId,
                    name: agentName,
                    start,
                    depot:
                      data.shift &&
                      Number.isFinite(data.shift.start_latitude) &&
                      Number.isFinite(data.shift.start_longitude)
                        ? {
                            latitude: data.shift.start_latitude,
                            longitude: data.shift.start_longitude,
                            label:
                              data.shift.start_location_label ??
                              "Configured shift depot",
                          }
                        : null,
                    is_active: true,
                    is_available:
                      data.reason === "shift_ended"
                        ? false
                        : (data.shift?.is_available ?? true),
                    region_code: data.shift?.region_code,
                    shift_label: data.reason === "shift_ended"
                      ? "Shift ended · existing assignments remain"
                      : data.shift
                        ? `${data.shift.is_available ? "Available" : "Unavailable"} · ${time(data.shift.shift_starts_at)}–${time(data.shift.shift_ends_at)}`
                        : "Shift status unavailable",
                  },
                ]}
                investigations={[
                  ...data.stops.map((stop) => ({
                    ...stop,
                    id: stop.investigation_id,
                    agent_id: agentId,
                    agent_name: agentName,
                  })),
                  ...cancelledInvestigations
                    .flatMap((item) =>
                      item.latitude == null || item.longitude == null
                        ? []
                        : [{
                            ...item,
                            latitude: item.latitude,
                            longitude: item.longitude,
                            agent_id: agentId,
                            agent_name: agentName,
                          }],
                    ),
                ]}
                routes={mapRoute ? [mapRoute] : []}
                selection={selection}
                onSelect={setSelection}
                onViewRoute={() => setTab("map")}
              />
            </div>
            {data.stops.length > 0 && (
              <ol className={`ordered-stops ${data.route ? "" : "route-unpublished-stops"}`}>
                {data.stops.map((stop) => (
                  <li
                    key={stop.investigation_id}
                    className={
                      selection?.type === "investigation" &&
                      selection.id === stop.investigation_id
                        ? "selected"
                        : ""
                    }
                    data-sequence-state={stop.sequence_state}
                  >
                    <button
                      className="stop-selection"
                      type="button"
                      onClick={() =>
                        setSelection({
                          type: "investigation",
                          id: stop.investigation_id,
                        })
                      }
                    >
                      <span className="stop-number">{stop.sequence ?? "—"}</span>
                      <span>
                        <span className="flex flex-wrap items-center gap-2">
                          <strong>{stop.reference_number}</strong>
                          <span
                            className={`priority-label priority-${stop.priority} shrink-0 rounded px-1.5 py-0.5 text-[10px] capitalize`}
                          >
                            {stop.priority}
                          </span>
                          <span className="count-badge">{({ current: "Current stop", upcoming: "Upcoming", deferred_retry: "Deferred retry", deferred: "Deferred", handled: "Handled" } as Record<string, string>)[stop.sequence_state]}</span>
                        </span>
                        <span>{stop.address_display}</span>
                      </span>
                    </button>
                    {data.route && <dl className="agent-stop-timings">
                      <div>
                        <dt>Travel from previous stop</dt>
                        <dd>{duration(stop.travel_seconds)}</dd>
                      </div>
                      <div>
                        <dt>Distance from previous stop</dt>
                        <dd>{distance(stop.travel_metres)}</dd>
                      </div>
                      <div>
                        <dt>
                          Earliest arrival estimate · depart as soon as possible
                        </dt>
                        <dd>
                          {time(
                            stop.earliest_arrival_estimate_at ??
                              stop.estimated_arrival_at,
                          )}
                        </dd>
                      </div>
                      <div>
                        <dt>Planned arrival</dt>
                        <dd>
                          {stop.planned_arrival_at
                            ? time(stop.planned_arrival_at)
                            : "Not available"}
                        </dd>
                      </div>
                      <div>
                        <dt>Wait at stop</dt>
                        <dd>{plannedWait(stop.planned_waiting_seconds)}</dd>
                      </div>
                      <div>
                        <dt>Service starts</dt>
                        <dd>
                          {stop.estimated_service_start_at
                            ? time(stop.estimated_service_start_at)
                            : "Not available"}
                        </dd>
                      </div>
                      <div>
                        <dt>Service ends</dt>
                        <dd>
                          {timeAfter(
                            stop.estimated_service_start_at,
                            stop.service_duration_seconds,
                          )}
                        </dd>
                      </div>
                      <div>
                        <dt>Investigation service</dt>
                        <dd>{duration(stop.service_duration_seconds)}</dd>
                      </div>
                    </dl>}
                    <div className="stop-actions">
                      <StatusBadge status={stop.status} />
                      <Link to={`/investigations/${stop.investigation_id}`}>
                        View investigation
                      </Link>
                    </div>
                    {stop.priority_order_exception_reason && (
                      <p className="form-hint">
                        Published order exception: {stop.priority_order_exception_reason === "assignment_time_constraint"
                          ? "an earlier assignment with the same priority stays first."
                          : stop.priority_order_exception_reason === "search_limit"
                            ? "the bounded search kept its best feasible order."
                            : "a visit window, shift hour, or break requires this order."}
                      </p>
                    )}
                    {stop.attempt_history?.length > 0 && (
                      <details className="workflow-meta">
                        <summary>Attempt history · {stop.attempt_history.length}</summary>
                        <ul>
                          {stop.attempt_history.map((attempt) => (
                            <li key={attempt.id}>
                              {attempt.event_type === "shift_end_not_visited" ? "Shift End — Not Visited" : reasonLabel(attempt.reason)}
                              {` · ${dateTimeLabel(attempt.attempted_at)} · ${attempt.state.replaceAll("_", " ")}`}
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </div>
        </>
      )}
    </div>
  );
}
