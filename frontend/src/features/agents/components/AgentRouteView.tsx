import { useState } from "react";
import { Link } from "react-router";
import type { AgentRoute } from "@/types/api";
import { OperationsMap } from "@/components/map/OperationsMap";
import "@/styles/planning.css";
import type { MapRoute, MapSelection } from "@/components/map/mapTypes";
import { EmptyState, InlineAlert, Tabs } from "@/components/ui/Primitives";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { distance, duration, time } from "@/utils/format";

function emptyCopy(reason: AgentRoute["reason"]) {
  if (reason === "no_shift") {
    return ["No shift configured", "A supervisor must configure a shift for this date."];
  }
  if (reason === "shift_unavailable") {
    return ["Shift unavailable", "This shift is not available for assignments."];
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
}: {
  data: AgentRoute;
  agentId: number;
  agentName: string;
}) {
  const [selection, setSelection] = useState<MapSelection>(null);
  const [tab, setTab] = useState("list");
  const start =
    data.route?.start ??
    (data.shift?.last_completed_latitude != null &&
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

  return (
    <div className="agent-route-view">
      {data.stops.length ? (
        <>
          <dl className="route-metrics">
            <div>
              <dt>{data.route ? "Published stops" : "Assigned investigations"}</dt>
              <dd>{data.stops.length}</dd>
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
              <dt>Waiting time</dt>
              <dd>{data.route ? duration(data.route.total_waiting_seconds) : "—"}</dd>
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
                been published. Their map pins remain visible; order and timing
                will appear after a successful route update.
              </InlineAlert>
            )
          )}
        </>
      ) : (
        <EmptyState title={cancelledInvestigations.length ? "Shift ended" : emptyTitle}>
          {cancelledInvestigations.length
            ? "Unfinished investigations are paused for the rest of this Manila workday and reopen on the date shown below."
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
                    is_available: data.shift?.is_available ?? true,
                    region_code: data.shift?.region_code,
                    shift_label: data.shift
                      ? `Available · ${time(data.shift.shift_starts_at)}–${time(data.shift.shift_ends_at)}`
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
                        <strong>{stop.reference_number}</strong>
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
                        <dt>Estimated arrival</dt>
                        <dd>{time(stop.estimated_arrival_at)}</dd>
                      </div>
                      <div>
                        <dt>Waiting</dt>
                        <dd>{duration(stop.waiting_seconds)}</dd>
                      </div>
                      <div>
                        <dt>Service starts</dt>
                        <dd>{time(stop.estimated_service_start_at ?? stop.estimated_arrival_at)}</dd>
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
