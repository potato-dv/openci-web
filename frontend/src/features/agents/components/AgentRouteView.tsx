import { useState } from "react";
import { Link } from "react-router";
import type { AgentRoute } from "@/types/api";
import { OperationsMap } from "@/components/map/OperationsMap";
import "@/styles/planning.css";
import type { MapSelection } from "@/components/map/mapTypes";
import { EmptyState, InlineAlert, Tabs } from "@/components/ui/Primitives";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { distance, duration, time } from "@/utils/format";
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
  if (!data.stops.length)
    return (
      <EmptyState
        title={
          data.reason === "no_shift"
            ? "No shift configured"
            : data.reason === "shift_unavailable"
              ? "Shift unavailable"
              : data.reason === "route_refresh_pending"
                ? "Route update in progress"
                : data.reason === "route_needs_refresh"
                  ? "Route needs an update"
                  : "No route stops"
        }
      >
        {data.reason === "no_shift"
          ? "A supervisor must configure a shift for this date."
          : data.reason === "shift_unavailable"
            ? "This shift is not available for assignments."
            : data.reason === "route_refresh_pending"
              ? "Your assignments have changed. A new road route will appear after the automatic route update finishes."
              : data.reason === "route_needs_refresh"
                ? "Your assignments have changed, but no current route is published. Ask a supervisor to retry route planning."
                : "Route stops appear here after automatic planning or an authorized manual override publishes an assignment."}
      </EmptyState>
    );
  const start =
    data.route?.start ??
    (data.shift
      ? {
          latitude: data.shift.start_latitude,
          longitude: data.shift.start_longitude,
          label: data.shift.start_location_label,
        }
      : null);
  return (
    <div className="agent-route-view">
      <dl className="route-metrics">
        <div>
          <dt>Published stops</dt>
          <dd>{data.stops.length}</dd>
        </div>
        <div>
          <dt>Road travel</dt>
          <dd>{duration(data.route?.total_travel_seconds)}</dd>
        </div>
        <div>
          <dt>Distance</dt>
          <dd>{distance(data.route?.total_distance_metres)}</dd>
        </div>
      </dl>
      <p className="form-hint">
        Starting point:{" "}
        {start?.label ||
          (start
            ? `${start.latitude.toFixed(5)}, ${start.longitude.toFixed(5)}`
            : "Unavailable")}{" "}
        · Estimated times use Philippine time.
      </p>
      {!data.route?.geometry && (
        <InlineAlert variant="warning">
          Road geometry is unavailable for this published route. The stop list
          is available below.
        </InlineAlert>
      )}
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
      <div className={`route-split active-${tab}`}>
        <div className="published-route-map">
          <OperationsMap
            agents={start ? [{
              id: agentId,
              name: agentName,
              start,
              is_active: true,
              is_available: data.shift?.is_available ?? true,
              region_code: data.shift?.region_code,
              shift_label: data.shift
                ? `Available · ${time(data.shift.shift_starts_at)}–${time(data.shift.shift_ends_at)}`
                : "Shift status unavailable",
            }] : []}
            investigations={data.stops.map((stop) => ({
              ...stop,
              id: stop.investigation_id,
              agent_id: agentId,
            }))}
            routes={data.route ? [data.route] : []}
            selection={selection}
            onSelect={setSelection}
            onViewRoute={() => setTab("list")}
          />
        </div>
        <ol className="ordered-stops">
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
                <span className="stop-number">{stop.sequence}</span>
                <span>
                  <strong>{stop.reference_number}</strong>
                  <span>{stop.address_display}</span>
                  <small>
                    Estimated arrival {time(stop.estimated_arrival_at)} ·{" "}
                    {duration(stop.travel_seconds)} /{" "}
                    {distance(stop.travel_metres)} from previous stop
                  </small>
                </span>
              </button>
              <div className="stop-actions">
                <StatusBadge status={stop.status} />
                <Link to={`/investigations/${stop.investigation_id}`}>
                  View investigation
                </Link>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
