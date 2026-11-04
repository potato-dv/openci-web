import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { createPortal } from "react-dom";
import { renderToStaticMarkup } from "react-dom/server";
import { divIcon, latLngBounds } from "leaflet";
import {
  MapContainer,
  Marker,
  Polygon,
  Polyline,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";
import {
  Check,
  Contrast,
  Layers,
  LocateFixed,
  MapPin,
  PersonStanding,
  Route,
  Search,
  Warehouse,
} from "lucide-react";
import { searchLocations } from "@/features/locations/api";
import type { GeocodeCandidate, PlanningReadiness } from "../../types/api";
import {
  ESTIMATED_TRAVELED_GRAY,
  ESTIMATED_TRAVELED_OPACITY,
  investigationPriorityColor,
  leafletPositions,
  routeColor,
  routeLineStyles,
  type MapAgent,
  type MapInvestigation,
  type MapRoute,
  type MapSelection,
  type RouteLineStyle,
} from "./mapTypes";
import { routesForSelection } from "./routeSelection";
import { IconButton } from "../ui/Primitives";
import { MapZoomControls } from "./MapZoomControls";
import { MapSizeInvalidator } from "./MapSizeInvalidator";
import "leaflet/dist/leaflet.css";
import "../../styles/maps.css";
type Props = {
  token?: string;
  agents?: MapAgent[];
  investigations?: MapInvestigation[];
  routes?: MapRoute[];
  density?: PlanningReadiness["density"];
  searchTarget?: HTMLElement | null;
  selection?: MapSelection;
  onSelect?: (selection: MapSelection) => void;
  onViewRoute?: (agentId: number) => void;
  showDensity?: boolean;
  showLegend?: boolean;
  showMarkerKey?: boolean;
  routeVisibility?: boolean;
  onRouteVisibilityChange?: (visible: boolean) => void;
  showRouteLayerToggle?: boolean;
  routeFitRequest?: { key: string; agentId: number | null } | null;
  clearSelectionOnBackgroundClick?: boolean;
  onDensityChange?: (show: boolean) => void;
  resolution?: 7 | 8 | 9;
  onResolutionChange?: (resolution: 7 | 8 | 9) => void;
  densityAvailable?: boolean;
  densityLoading?: boolean;
  densityError?: string;
};
function icon(
  type: "agent" | "investigation",
  text: string,
  selected: boolean,
  included: boolean,
  color: string,
  glyphColor = "#fff",
  reviewPending = false,
  offsetX = 0,
) {
  const isAgent = type === "agent";
  return divIcon({
    className: `map-symbol ${type} ${selected ? "selected" : ""} ${included ? "included" : "not-included"} ${reviewPending ? "review-pending" : ""}`,
    iconSize: [36, 42],
    // Offset colliding icons horizontally without changing their map position.
    iconAnchor: [18 - offsetX, 36],
    html: renderToStaticMarkup(
      <span>
        <span
          className="symbol-icon"
          style={{
            backgroundColor: isAgent ? "#4285f4" : color,
            borderColor: isAgent ? "#1a73e8" : color,
            color: isAgent ? "#fff" : glyphColor,
          }}
        >
          {type === "agent" ? (
            <PersonStanding size={28} strokeWidth={2} />
          ) : (
            <MapPin size={28} strokeWidth={1.8} />
          )}
        </span>
        {!isAgent && text && (
          <b style={{ backgroundColor: color, color: glyphColor }}>{text}</b>
        )}
      </span>,
    ),
  });
}
export function AgentMarker({
  agent,
  selected,
  index,
  offsetX = 0,
  onSelect,
}: {
  agent: MapAgent;
  selected: boolean;
  index: number;
  offsetX?: number;
  onSelect?: Props["onSelect"];
}) {
  const availability =
    agent.is_active === false
      ? "Inactive agent"
      : agent.is_available === true
        ? "Available shift"
        : agent.is_available === false
          ? "Unavailable shift"
          : "No shift status";
  const routeStatus = {
    none: "No route published",
    queued: "Route update queued",
    running: "Route is being built",
    published: "Route published",
    failed: "Route update failed",
    partially_published: "Some routes need attention",
    needs_refresh: "Route needs an update",
  }[agent.route_status ?? "none"];
  const description = [
    agent.name,
    availability,
    agent.region_label,
    routeStatus,
    agent.start.label ?? "Configured shift starting point",
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <Marker
      position={[agent.start.latitude, agent.start.longitude]}
      bubblingMouseEvents={false}
      icon={icon(
        "agent",
        String(index + 1),
        selected,
        true,
        routeColor(agent.id),
        "#fff",
        false,
        offsetX,
      )}
      title={description}
      keyboard
      eventHandlers={{
        add: (event) =>
          event.target.getElement()?.setAttribute("aria-label", description),
        click: () => onSelect?.({ type: "agent", id: agent.id }),
      }}
    >
      <Tooltip>{description}</Tooltip>
    </Marker>
  );
}

function depotIcon(offsetX = 0) {
  return divIcon({
    className: "map-symbol depot",
    iconSize: [36, 42],
    iconAnchor: [18 - offsetX, 36],
    html: renderToStaticMarkup(
      <span>
        <span className="depot-symbol-icon">
          <Warehouse size={19} strokeWidth={2} />
        </span>
      </span>,
    ),
  });
}

function DepotMarker({
  agent,
  offsetX = 0,
}: {
  agent: MapAgent;
  offsetX?: number;
}) {
  if (!agent.depot) return null;
  const description = `${agent.name} · Configured shift depot${agent.depot.label ? ` · ${agent.depot.label}` : ""}`;
  return (
    <Marker
      position={[agent.depot.latitude, agent.depot.longitude]}
      bubblingMouseEvents={false}
      icon={depotIcon(offsetX)}
      title={description}
      keyboard
      eventHandlers={{
        add: (event) =>
          event.target.getElement()?.setAttribute("aria-label", description),
      }}
    >
      <Tooltip>{description}</Tooltip>
    </Marker>
  );
}
export function InvestigationMarker({
  item,
  selected,
  included,
  color,
  offsetX = 0,
  onSelect,
}: {
  item: MapInvestigation;
  selected: boolean;
  included: boolean;
  color: string;
  offsetX?: number;
  onSelect?: Props["onSelect"];
}) {
  const assignment = item.agent_id
    ? `Assigned to ${item.agent_name ?? `Agent ${item.agent_id}`}`
    : "Unassigned";
  const routeStop = item.sequence ? `Stop ${item.sequence}` : null;
  const statusLabel = item.status.replaceAll("_", " ");
  const markerLabel = `${item.reference_number} · ${item.region_label ?? "Region not set"} · ${statusLabel} · ${item.planning_status ?? (item.agent_id ? "assigned" : "pending")} · ${assignment}${routeStop ? ` · ${routeStop}` : ""} · ${item.priority} priority${item.planning_reason ? ` · ${item.planning_reason.replaceAll("_", " ")}` : ""}`;
  return (
    <Marker
      position={[item.latitude, item.longitude]}
      bubblingMouseEvents={false}
      icon={icon(
        "investigation",
        item.sequence
          ? String(item.sequence)
          : item.priority === "urgent"
            ? "!"
            : "",
        selected,
        included,
        color,
        item.priority === "high" ? "#302400" : "#fff",
        ["under_review", "returned_for_correction", "completed", "cancelled"].includes(
          item.status,
        ),
        offsetX,
      )}
      title={markerLabel}
      keyboard
      eventHandlers={{
        add: (event) =>
          event.target
            .getElement()
            ?.setAttribute(
              "aria-label",
              markerLabel,
            ),
        click: () => onSelect?.({ type: "investigation", id: item.id }),
      }}
    >
      <Tooltip>
        {item.reference_number} · {item.region_label ?? "Region not set"} ·{" "}
        {statusLabel} ·{" "}
        {item.planning_status ?? (item.agent_id ? "assigned" : "pending")} ·{" "}
        {assignment}
        {routeStop ? ` · ${routeStop}` : ""} · {item.priority} priority
        {item.planning_reason
          ? ` · ${item.planning_reason.replaceAll("_", " ")}`
          : ""}
      </Tooltip>
    </Marker>
  );
}
export function RouteLayer({
  route,
  style,
  selected,
  onSelect,
}: {
  route: MapRoute;
  style: RouteLineStyle;
  selected: boolean;
  onSelect?: Props["onSelect"];
}) {
  const completedPositions = route.completed_geometry
    ? leafletPositions(route.completed_geometry)
    : null;
  const positions = route.geometry ? leafletPositions(route.geometry) : null;
  if (!completedPositions && !positions) return null;
  return (
    <>
      {completedPositions && (
        <Polyline
          positions={completedPositions}
          pathOptions={{
            color: ESTIMATED_TRAVELED_GRAY,
            weight: selected ? 6 : 4,
            opacity: ESTIMATED_TRAVELED_OPACITY,
            interactive: true,
            bubblingMouseEvents: false,
          }}
          eventHandlers={{
            click: () => onSelect?.({ type: "agent", id: route.agent_id }),
          }}
        />
      )}
      {positions && (
        <Polyline
          positions={positions}
          pathOptions={{
            color: style.color,
            dashArray: style.dashArray,
            weight: selected ? 7 : 5,
            opacity: 1,
            interactive: true,
            bubblingMouseEvents: false,
          }}
          eventHandlers={{
            click: () => onSelect?.({ type: "agent", id: route.agent_id }),
          }}
        />
      )}
    </>
  );
}

function routePositions(route: MapRoute): [number, number][] {
  return [route.completed_geometry, route.geometry]
    .filter((geometry): geometry is NonNullable<typeof geometry> => !!geometry)
    .flatMap(leafletPositions);
}

export function H3Layer({
  density,
}: {
  density: PlanningReadiness["density"];
}) {
  return (
    <>
      {density.map((cell) => (
        <Polygon
          key={cell.cell}
          positions={cell.geometry.coordinates.map((ring) =>
            ring.map(([lon, lat]) => [lat, lon] as [number, number]),
          )}
          pathOptions={{
            color: "#5e6ad2",
            weight: 1,
            fillOpacity: Math.min(0.3, 0.06 + cell.count * 0.025),
          }}
        >
          <Tooltip permanent direction="center" className="density-label">
            {cell.count}
          </Tooltip>
        </Polygon>
      ))}
    </>
  );
}
function ViewportMarkers({
  agents,
  investigations,
  selection,
  onSelect,
}: Required<Pick<Props, "agents" | "investigations">> &
  Pick<Props, "selection" | "onSelect">) {
  const map = useMap();
  const [bounds, setBounds] = useState(map.getBounds());
  const visibleAgents = useMemo(
    () =>
      agents.filter((agent) =>
        bounds.contains([agent.start.latitude, agent.start.longitude]),
      ),
    [agents, bounds],
  );
  const visibleInvestigations = useMemo(
    () =>
      investigations.filter((item) =>
        bounds.contains([item.latitude, item.longitude]),
      ),
    [bounds, investigations],
  );
  const selectedAgent =
    selection?.type === "agent"
      ? agents.find((agent) => agent.id === selection.id)
      : undefined;
  const visibleDepot =
    selectedAgent?.depot &&
    bounds.contains([
      selectedAgent.depot.latitude,
      selectedAgent.depot.longitude,
    ])
      ? selectedAgent
      : undefined;
  const markerOffsets = useMemo(() => {
    const markers = [
      ...visibleAgents.map((agent) => ({
        key: `agent:${agent.id}`,
        latitude: agent.start.latitude,
        longitude: agent.start.longitude,
      })),
      ...visibleInvestigations.map((item) => ({
        key: `investigation:${item.id}`,
        latitude: item.latitude,
        longitude: item.longitude,
      })),
      ...(visibleDepot?.depot
        ? [
            {
              key: `depot:${visibleDepot.id}`,
              latitude: visibleDepot.depot.latitude,
              longitude: visibleDepot.depot.longitude,
            },
          ]
        : []),
    ];
    const spacing = 42;
    const radiusSquared = spacing * spacing;
    const zoom = map.getZoom();
    const offsets = new Map<string, number>();
    const coincident = new Map<string, number[]>();
    markers.forEach((marker, index) => {
      const pointKey = `${marker.latitude}:${marker.longitude}`;
      const group = coincident.get(pointKey);
      if (group) group.push(index);
      else coincident.set(pointKey, [index]);
    });
    for (const group of coincident.values()) {
      if (
        group.length < 2 ||
        !group.some((index) => markers[index].key.startsWith("depot:"))
      )
        continue;
      group.forEach((markerIndex, position) => {
        offsets.set(
          markers[markerIndex].key,
          (position - (group.length - 1) / 2) * spacing,
        );
      });
    }
    if (zoom < 11 || markers.length < 2) return offsets;

    const projected = markers.map((marker) =>
      map.project([marker.latitude, marker.longitude], zoom),
    );
    const parents = markers.map((_marker, index) => index);
    const find = (index: number): number => {
      if (parents[index] !== index) parents[index] = find(parents[index]);
      return parents[index];
    };
    const join = (left: number, right: number) => {
      const leftRoot = find(left);
      const rightRoot = find(right);
      if (leftRoot !== rightRoot) parents[rightRoot] = leftRoot;
    };
    const buckets = new Map<string, number[]>();
    for (let index = 0; index < markers.length; index += 1) {
      const point = projected[index];
      const cellX = Math.floor(point.x / spacing);
      const cellY = Math.floor(point.y / spacing);
      for (let x = cellX - 1; x <= cellX + 1; x += 1) {
        for (let y = cellY - 1; y <= cellY + 1; y += 1) {
          for (const candidate of buckets.get(`${x}:${y}`) ?? []) {
            const other = projected[candidate];
            const dx = point.x - other.x;
            const dy = point.y - other.y;
            if (dx * dx + dy * dy < radiusSquared) join(index, candidate);
          }
        }
      }
      const bucket = `${cellX}:${cellY}`;
      const bucketMarkers = buckets.get(bucket);
      if (bucketMarkers) bucketMarkers.push(index);
      else buckets.set(bucket, [index]);
    }

    const groups = new Map<number, number[]>();
    markers.forEach((_marker, index) => {
      const root = find(index);
      const group = groups.get(root);
      if (group) group.push(index);
      else groups.set(root, [index]);
    });
    offsets.clear();
    for (const group of groups.values()) {
      if (group.length < 2) continue;
      group.forEach((markerIndex, position) => {
        offsets.set(
          markers[markerIndex].key,
          (position - (group.length - 1) / 2) * spacing,
        );
      });
    }
    return offsets;
  }, [map, visibleAgents, visibleDepot, visibleInvestigations]);
  useMapEvents({
    moveend: () => setBounds(map.getBounds().pad(0.15)),
    zoomend: () => setBounds(map.getBounds().pad(0.15)),
    resize: () => setBounds(map.getBounds().pad(0.15)),
  });
  return (
    <>
      {visibleAgents.map((agent) => (
          <AgentMarker
            key={agent.id}
            agent={agent}
            index={agents.findIndex((item) => item.id === agent.id)}
            offsetX={markerOffsets.get(`agent:${agent.id}`) ?? 0}
            selected={selection?.type === "agent" && selection.id === agent.id}
            onSelect={onSelect}
          />
        ))}
      {visibleInvestigations.map((item) => (
          <InvestigationMarker
            key={item.id}
            item={item}
            color={investigationPriorityColor(item.priority)}
            offsetX={markerOffsets.get(`investigation:${item.id}`) ?? 0}
            included={
              selection?.type !== "agent" || item.agent_id === selection.id
            }
            selected={
              selection?.type === "investigation" && selection.id === item.id
            }
            onSelect={onSelect}
          />
        ))}
      {visibleDepot && (
        <DepotMarker
          key={`depot:${visibleDepot.id}`}
          agent={visibleDepot}
          offsetX={markerOffsets.get(`depot:${visibleDepot.id}`) ?? 0}
        />
      )}
    </>
  );
}

export function BackgroundSelectionReset({
  onSelect,
}: Pick<Props, "onSelect">) {
  useMapEvents({
    click: () => onSelect?.(null),
  });
  return null;
}

function MapControls({
  agents,
  investigations,
  routes,
  selection,
  routesVisible,
  routeFitRequest,
}: Pick<Props, "selection"> &
  Required<Pick<Props, "agents" | "investigations" | "routes">> &
  Pick<Props, "routeFitRequest"> & { routesVisible: boolean }) {
  const map = useMap();
  const lastFitRequestKey = useRef<string | null>(null);
  const selectedPoint =
    selection?.type === "agent"
      ? agents.find((agent) => agent.id === selection.id)?.start
      : selection?.type === "investigation"
        ? investigations.find((item) => item.id === selection.id)
        : null;
  const selectedRouteAgentId =
    routeFitRequest?.agentId ??
    (selection?.type === "agent"
      ? selection.id
      : selection?.type === "investigation"
        ? (investigations.find((item) => item.id === selection.id)?.agent_id ??
          null)
        : null);
  const selectedRouteAgent =
    selection?.type === "agent"
      ? agents.find((agent) => agent.id === selection.id)
      : null;
  const selectionType = selection?.type ?? null;
  const selectionId = selection?.id ?? null;
  const selectionKey = selection ? `${selection.type}:${selection.id}` : null;
  const lastSelectionFitKey = useRef<string | null>(null);
  const routeFocusActive = selection !== null;
  const routesInFocus = !routeFocusActive
    ? routes
    : selectedRouteAgentId == null
      ? []
      : routes.filter((route) => route.agent_id === selectedRouteAgentId);
  const pointKey = [
    ...agents.map((item) => `${item.start.latitude}:${item.start.longitude}`),
    ...investigations.map((item) => `${item.latitude}:${item.longitude}`),
  ].join("|");
  useEffect(() => {
    if (routeFitRequest !== undefined) return;
    const points = pointKey
      .split("|")
      .filter(Boolean)
      .map((point) => point.split(":").map(Number) as [number, number]);
    function fit() {
      map.invalidateSize();
      if (
        points.length &&
        map.getContainer().clientWidth &&
        map.getContainer().clientHeight
      )
        map.fitBounds(latLngBounds(points), {
          padding: [40, 40],
          maxZoom: 15,
          animate: false,
        });
    }
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [map, pointKey, routeFitRequest]);

  useEffect(() => {
    if (!routeFitRequest || !routesVisible) {
      lastFitRequestKey.current = null;
      return;
    }
    if (lastFitRequestKey.current === routeFitRequest.key) return;

    const focused = selection !== null || selectedRouteAgentId != null;
    const selectedAgent =
      selectedRouteAgentId == null
        ? null
        : agents.find((agent) => agent.id === selectedRouteAgentId);
    const selectedDepot =
      selection?.type === "agent" ? selectedAgent?.depot : null;
    const selectedInvestigation =
      selection?.type === "investigation"
        ? investigations.find((item) => item.id === selection.id)
        : null;
    const relevantRoutes = !focused
      ? routes
      : selectedRouteAgentId == null
        ? []
        : routes.filter((route) => route.agent_id === selectedRouteAgentId);
    const routePoints = relevantRoutes.flatMap(routePositions);
    const selectedStopPoint = selectedInvestigation
      ? [
          [selectedInvestigation.latitude, selectedInvestigation.longitude] as [
            number,
            number,
          ],
        ]
      : [];
    const points = !focused
      ? routePoints
      : [
          ...(selectedAgent
            ? [
                [
                  selectedAgent.start.latitude,
                  selectedAgent.start.longitude,
                ] as [number, number],
              ]
            : []),
          ...(selectedDepot
            ? [
                [selectedDepot.latitude, selectedDepot.longitude] as [
                  number,
                  number,
                ],
              ]
            : []),
          ...selectedStopPoint,
          ...routePoints,
        ];
    const fallbackPoints = focused
      ? [
          ...(selectedAgent
            ? [
                [
                  selectedAgent.start.latitude,
                  selectedAgent.start.longitude,
                ] as [number, number],
              ]
            : []),
          ...(selectedDepot
            ? [
                [selectedDepot.latitude, selectedDepot.longitude] as [
                  number,
                  number,
                ],
              ]
            : []),
          ...selectedStopPoint,
        ]
      : [
          ...agents.map(
            (agent) =>
              [agent.start.latitude, agent.start.longitude] as [number, number],
          ),
          ...investigations.map(
            (item) => [item.latitude, item.longitude] as [number, number],
          ),
        ];
    const fitPoints = points.length ? points : fallbackPoints;
    const container = map.getContainer();
    let disposed = false;
    let frame: number | null = null;
    const fitWhenVisible = () => {
      if (lastFitRequestKey.current === routeFitRequest.key) return true;
      if (!fitPoints.length) {
        lastFitRequestKey.current = routeFitRequest.key;
        return true;
      }
      if (!container.clientWidth || !container.clientHeight) return false;

      map.invalidateSize();
      frame = requestAnimationFrame(() => {
        if (disposed) return;
        map.fitBounds(latLngBounds(fitPoints), {
          padding: [40, 40],
          maxZoom: focused ? 16 : 14,
          animate: false,
        });
        lastFitRequestKey.current = routeFitRequest.key;
      });
      return true;
    };
    if (fitWhenVisible())
      return () => {
        disposed = true;
        if (frame != null) cancelAnimationFrame(frame);
      };

    const observer = new ResizeObserver(() => {
      if (fitWhenVisible()) observer.disconnect();
    });
    observer.observe(container);
    return () => {
      disposed = true;
      observer.disconnect();
      if (frame != null) cancelAnimationFrame(frame);
    };
  }, [
    agents,
    investigations,
    map,
    routeFitRequest,
    routes,
    routesVisible,
    selectedRouteAgentId,
    selection,
  ]);

  useEffect(() => {
    if (routeFitRequest !== undefined) return;
    if (!selectionKey) {
      lastSelectionFitKey.current = null;
      return;
    }
    if (lastSelectionFitKey.current === selectionKey) return;

    const selectedAgent =
      selectionType === "agent" && selectionId != null
        ? agents.find((agent) => agent.id === selectionId)
        : null;
    const selectedInvestigation =
      selectionType === "investigation" && selectionId != null
        ? investigations.find((item) => item.id === selectionId)
        : null;
    const focusedRoutes =
      selectedRouteAgentId == null
        ? []
        : routes.filter((route) => route.agent_id === selectedRouteAgentId);
    const points: [number, number][] = [
      ...focusedRoutes.flatMap(routePositions),
      ...(selectedAgent
        ? [
            [selectedAgent.start.latitude, selectedAgent.start.longitude] as [
              number,
              number,
            ],
            ...(selectedAgent.depot
              ? [
                  [
                    selectedAgent.depot.latitude,
                    selectedAgent.depot.longitude,
                  ] as [number, number],
                ]
              : []),
          ]
        : []),
      ...(selectedInvestigation
        ? [
            [
              selectedInvestigation.latitude,
              selectedInvestigation.longitude,
            ] as [number, number],
          ]
        : []),
    ];
    if (points.length) {
      map.fitBounds(latLngBounds(points), {
        padding: [40, 40],
        maxZoom: 16,
        animate: false,
      });
    }
    lastSelectionFitKey.current = selectionKey;
  }, [
    agents,
    investigations,
    map,
    routeFitRequest,
    routes,
    selectedRouteAgentId,
    selectionKey,
    selectionId,
    selectionType,
  ]);

  function fitRoute() {
    const points = [
      ...routesInFocus.flatMap(routePositions),
      ...(selectedRouteAgent
        ? [
            [
              selectedRouteAgent.start.latitude,
              selectedRouteAgent.start.longitude,
            ] as [number, number],
          ]
        : []),
      ...(selectedRouteAgent?.depot
        ? [
            [
              selectedRouteAgent.depot.latitude,
              selectedRouteAgent.depot.longitude,
            ] as [number, number],
          ]
        : []),
    ];
    if (points.length)
      map.fitBounds(latLngBounds(points), {
        padding: [40, 40],
        maxZoom: 16,
        animate: false,
      });
  }
  function fitAll() {
    const points = [
      ...agents.map(
        (item) =>
          [item.start.latitude, item.start.longitude] as [number, number],
      ),
      ...investigations.map(
        (item) => [item.latitude, item.longitude] as [number, number],
      ),
    ];
    if (points.length)
      map.fitBounds(latLngBounds(points), {
        padding: [40, 40],
        maxZoom: 15,
        animate: false,
      });
  }
  function fitSelection() {
    const point =
      selection?.type === "agent"
        ? agents.find((agent) => agent.id === selection.id)?.start
        : investigations.find((item) => item.id === selection?.id);
    if (point)
      map.setView([point.latitude, point.longitude], 15, { animate: false });
  }
  return (
    <div className="map-fit-controls">
      <IconButton
        label="Fit all planning points"
        onClick={fitAll}
        disabled={!agents.length && !investigations.length}
      >
        <MapPin size={18} />
      </IconButton>
      <IconButton
        label="Fit to route"
        onClick={fitRoute}
        disabled={
          !routesVisible || !routesInFocus.some(
            (route) => route.geometry || route.completed_geometry,
          )
        }
      >
        <Route size={18} />
      </IconButton>
      <IconButton
        label="Fit to selected marker"
        onClick={fitSelection}
        disabled={!selectedPoint}
      >
        <LocateFixed size={18} />
      </IconButton>
    </div>
  );
}

type MapSearchResult = {
  key: string;
  label: string;
  detail: string;
  latitude: number;
  longitude: number;
  selection: MapSelection;
};

function MapSearchControl({
  token,
  agents,
  investigations,
  onSelect,
  searchTarget,
}: {
  token?: string;
  agents: MapAgent[];
  investigations: MapInvestigation[];
  onSelect?: Props["onSelect"];
  searchTarget?: HTMLElement | null;
}) {
  const map = useMap();
  const [query, setQuery] = useState("");
  const [placeResults, setPlaceResults] = useState<GeocodeCandidate[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [showResults, setShowResults] = useState(false);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);

  const recordResults = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (normalized.length < 2) return [];
    const caseResults = investigations
      .filter((item) =>
        `${item.reference_number} ${item.address_display} ${item.agent_name ?? ""}`
          .toLocaleLowerCase()
          .includes(normalized),
      )
      .map((item): MapSearchResult => ({
        key: `case-${item.id}`,
        label: item.reference_number,
        detail: item.address_display,
        latitude: item.latitude,
        longitude: item.longitude,
        selection: { type: "investigation", id: item.id },
      }));
    const agentResults = agents
      .filter((item) =>
        `${item.name} ${item.region_label ?? ""}`
          .toLocaleLowerCase()
          .includes(normalized),
      )
      .map((item): MapSearchResult => ({
        key: `agent-${item.id}`,
        label: item.name,
        detail: item.region_label ?? "Agent starting point",
        latitude: item.start.latitude,
        longitude: item.start.longitude,
        selection: { type: "agent", id: item.id },
      }));
    return [...caseResults, ...agentResults].slice(0, 5);
  }, [agents, investigations, query]);

  function focus(latitude: number, longitude: number, selection: MapSelection) {
    map.flyTo([latitude, longitude], Math.max(14, map.getZoom()), {
      duration: 0.35,
    });
    if (selection) onSelect?.(selection);
    setShowResults(false);
    setPlaceResults([]);
    setSearchError("");
  }

  async function searchPlaces(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = query.trim();
    if (!value) return;
    if (
      recordResults.length === 1 &&
      recordResults[0].label.toLocaleLowerCase() === value.toLocaleLowerCase()
    ) {
      const result = recordResults[0];
      focus(result.latitude, result.longitude, result.selection);
      return;
    }
    if (!token) {
      setSearchError(
        "Address search is unavailable. Use a record match or check the location service.",
      );
      setShowResults(true);
      return;
    }
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setSearching(true);
    setSearchError("");
    setPlaceResults([]);
    setShowResults(true);
    try {
      const results = await searchLocations(token, value, controller.signal);
      if (!controller.signal.aborted) setPlaceResults(results);
    } catch (error) {
      if (!controller.signal.aborted) {
        setSearchError(
          error instanceof Error
            ? error.message
            : "Address search failed. Try again.",
        );
      }
    } finally {
      if (!controller.signal.aborted) setSearching(false);
    }
  }

  const searchControl = (
    <div
      className={
        searchTarget
          ? "map-search-control relative! top-auto! left-auto! right-auto! z-[1500]! w-full! min-w-0!"
          : "map-search-control"
      }
      onMouseDown={(event) => event.stopPropagation()}
    >
      <form
        className="map-search-form"
        role="search"
        onSubmit={(event) => void searchPlaces(event)}
      >
        <Search size={17} aria-hidden="true" />
        <input
          aria-label="Search addresses or records on the map"
          value={query}
          onFocus={() => setShowResults(true)}
          onChange={(event) => {
            request.current?.abort();
            request.current = null;
            setQuery(event.target.value);
            setSearching(false);
            setPlaceResults([]);
            setSearchError("");
            setShowResults(true);
          }}
          placeholder="Search address or reference…"
        />
        <button
          type="submit"
          aria-label="Search address"
          disabled={searching || query.trim().length < 3}
        >
          {searching ? (
            <span className="map-search-spinner" aria-hidden="true" />
          ) : (
            <Search size={16} aria-hidden="true" />
          )}
        </button>
      </form>
      {showResults && query.trim().length >= 2 && (
        <div
          className={
            searchTarget
              ? "map-search-results absolute! left-0! right-0! top-full! z-[1500]! mt-1!"
              : "map-search-results"
          }
          role="region"
          aria-label="Map search results"
        >
          {recordResults.map((result) => (
            <button
              key={result.key}
              type="button"
              onClick={() =>
                focus(result.latitude, result.longitude, result.selection)
              }
            >
              <strong>{result.label}</strong>
              <span>{result.detail}</span>
            </button>
          ))}
          {placeResults.map((result) => (
            <button
              key={result.provider_ref ?? result.label}
              type="button"
              onClick={() => focus(result.latitude, result.longitude, null)}
            >
              <strong>{result.label}</strong>
              <span>{result.category ?? "Address result"}</span>
            </button>
          ))}
          {searching && <p role="status">Searching addresses…</p>}
          {searchError && (
            <p className="map-search-error" role="alert">
              {searchError}
            </p>
          )}
          {!searching &&
            !searchError &&
            !placeResults.length &&
            !recordResults.length && (
              <p>
                {query.trim().length < 3
                  ? "Enter at least 3 characters to search addresses."
                  : "No matching records yet. Press Enter to search addresses."}
              </p>
            )}
        </div>
      )}
    </div>
  );
  if (searchTarget === null) return null;
  return searchTarget
    ? createPortal(searchControl, searchTarget)
    : searchControl;
}

export function MapLegend({
  routes,
  routeStyles,
  showMarkerKey = true,
  showDepotKey = false,
}: {
  routes: MapRoute[];
  routeStyles: Map<number, RouteLineStyle>;
  showMarkerKey?: boolean;
  showDepotKey?: boolean;
}) {
  const routedAgents = routes.filter(
    (route) => route.geometry || route.completed_geometry,
  );
  return (
    <div className="map-legend" aria-label="Route legend">
      {showMarkerKey && (
        <>
          <strong>Map key</strong>
          <span>
            <i className="map-key-symbol agent" />
            Blue person marker · effective route origin
          </span>
          <span>
            <i className="map-key-symbol investigation" />
            Investigation priority
          </span>
          <span
            className="map-priority-key"
            aria-label="Investigation priority colors"
          >
            <i style={{ backgroundColor: investigationPriorityColor("normal") }} />
            Normal
            <i style={{ backgroundColor: investigationPriorityColor("high") }} />
            High
            <i style={{ backgroundColor: investigationPriorityColor("urgent") }} />
            Urgent
          </span>
        </>
      )}
      {showDepotKey && (
        <>
          {!showMarkerKey && <strong>Selected agent</strong>}
          <span>
            <i className="map-key-symbol depot" />
            Gray warehouse marker · configured shift depot
          </span>
        </>
      )}
      {routedAgents.length > 0 && (
        <>
          <strong>Road routes</strong>
          {routedAgents.filter((route) => route.geometry).map((route) => {
            const style = routeStyles.get(route.agent_id) ?? {
              color: routeColor(route.agent_id),
            };
            const [dashLength, gapLength] = (style.dashArray ?? "")
              .split(" ")
              .map(Number);
            return (
              <span key={route.agent_id}>
                <i
                  className="map-route-key"
                  style={{
                    backgroundColor: style.dashArray
                      ? "transparent"
                      : style.color,
                    backgroundImage: style.dashArray
                      ? `repeating-linear-gradient(to right, ${style.color} 0 ${dashLength}px, transparent ${dashLength}px ${dashLength + gapLength}px)`
                      : "none",
                  }}
                />
                {route.agent_name} · Remaining route
              </span>
            );
          })}
          {routedAgents.some((route) => route.completed_geometry) && (
            <span>
              <i
                className="map-route-key map-route-key-completed"
                aria-hidden="true"
              />
              Estimated traveled route
            </span>
          )}
        </>
      )}
    </div>
  );
}
export function OperationsMap({
  token,
  searchTarget,
  agents = [],
  investigations = [],
  routes = [],
  density = [],
  selection = null,
  onSelect,
  onViewRoute,
  showDensity = false,
  showLegend = true,
  showMarkerKey = true,
  routeVisibility,
  onRouteVisibilityChange,
  showRouteLayerToggle = true,
  routeFitRequest,
  clearSelectionOnBackgroundClick = false,
  onDensityChange,
  resolution = 8,
  onResolutionChange,
  densityAvailable = density.length > 0,
  densityLoading = false,
  densityError = "",
}: Props) {
  const [layersOpen, setLayersOpen] = useState(false);
  const [tilesFailed, setTilesFailed] = useState(false);
  const [tileVersion, setTileVersion] = useState(0);
  const [baseStyle, setBaseStyle] = useState<"streets" | "high-contrast">(
    "streets",
  );
  const [showLocalDensity, setShowLocalDensity] = useState(false);
  const [showAgents, setShowAgents] = useState(true);
  const [showInvestigations, setShowInvestigations] = useState(true);
  const [showRoutes, setShowRoutes] = useState(true);
  const routesVisible = routeVisibility ?? showRoutes;
  const lineStyles = useMemo(() => routeLineStyles(routes), [routes]);
  const selectFromMap = useCallback(
    (next: MapSelection) => {
      onSelect?.(next);
      if (next?.type === "agent") onViewRoute?.(next.id);
    },
    [onSelect, onViewRoute],
  );
  const densityVisible = onDensityChange ? showDensity : showLocalDensity;
  function toggleDensity(checked: boolean) {
    setShowLocalDensity(checked);
    onDensityChange?.(checked);
  }
  function toggleRoutes(visible: boolean) {
    if (routeVisibility === undefined) setShowRoutes(visible);
    onRouteVisibilityChange?.(visible);
  }
  const highlightedAgentId =
    selection?.type === "agent"
      ? selection.id
      : selection?.type === "investigation"
        ? (investigations.find((item) => item.id === selection.id)?.agent_id ??
          null)
        : null;
  const showSelectedDepot =
    selection?.type === "agent" &&
    agents.some((agent) => agent.id === selection.id && agent.depot != null);
  const renderRoutes = useMemo(() => {
    const focusedRoutes = routesForSelection(routes, selection, investigations);
    return [...focusedRoutes].sort(
      (left, right) =>
        Number(left.agent_id === highlightedAgentId) -
        Number(right.agent_id === highlightedAgentId),
    );
  }, [highlightedAgentId, investigations, routes, selection]);
  return (
    <div
      className={`operations-map ${baseStyle === "high-contrast" ? "map-style-high-contrast" : ""}`}
      aria-label="Investigation and route map"
    >
      <MapContainer
        center={[12.5, 122]}
        zoom={6}
        zoomControl={false}
        scrollWheelZoom
        className="leaflet-map"
      >
        <MapSizeInvalidator />
        <MapZoomControls />
        <MapSearchControl
          token={token}
          agents={agents}
          investigations={investigations}
          onSelect={selectFromMap}
          searchTarget={searchTarget}
        />
        <TileLayer
          key={tileVersion}
          url={
            import.meta.env.VITE_MAP_TILE_URL ||
            "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          }
          attribution={
            import.meta.env.VITE_MAP_TILE_ATTRIBUTION ||
            '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          }
          eventHandlers={{
            tileerror: () => setTilesFailed(true),
            load: () => setTilesFailed(false),
          }}
        />
        {densityVisible && density.length > 0 && <H3Layer density={density} />}
        {routesVisible &&
          renderRoutes.map((route) => (
            <RouteLayer
              key={route.agent_id}
              route={route}
              style={
                lineStyles.get(route.agent_id) ?? {
                  color: routeColor(route.agent_id),
                }
              }
              selected={highlightedAgentId === route.agent_id}
              onSelect={selectFromMap}
            />
          ))}
        <ViewportMarkers
          agents={showAgents ? agents : []}
          investigations={showInvestigations ? investigations : []}
          selection={selection}
          onSelect={selectFromMap}
        />
        {clearSelectionOnBackgroundClick && (
          <BackgroundSelectionReset onSelect={selectFromMap} />
        )}
        <MapControls
          agents={agents}
          investigations={investigations}
          routes={routes}
          selection={selection}
          routesVisible={routesVisible}
          routeFitRequest={routeFitRequest}
        />
      </MapContainer>
      <div className="map-layer-control">
        <IconButton
          className="transition-all duration-150 hover:border-openci-accent! hover:bg-openci-surface-selected! hover:text-openci-accent-strong! hover:shadow-lg! focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-openci-accent"
          label="Map layers and style"
          onClick={() => setLayersOpen((value) => !value)}
          aria-expanded={layersOpen}
        >
          <Layers size={18} />
        </IconButton>
        {layersOpen && (
          <div className="layer-menu">
            <fieldset className="map-style-options">
              <legend>Map style</legend>
              <button
                type="button"
                aria-pressed={baseStyle === "streets"}
                onClick={() => setBaseStyle("streets")}
              >
                <span>Streets</span>
                {baseStyle === "streets" && (
                  <Check size={15} aria-hidden="true" />
                )}
              </button>
              <button
                type="button"
                aria-pressed={baseStyle === "high-contrast"}
                onClick={() => setBaseStyle("high-contrast")}
              >
                <span>
                  <Contrast size={15} aria-hidden="true" /> High contrast
                </span>
                {baseStyle === "high-contrast" && (
                  <Check size={15} aria-hidden="true" />
                )}
              </button>
            </fieldset>
            <div className="layer-divider" />
            <strong>Show on map</strong>
            <label className="check-row">
              <input
                type="checkbox"
                checked={showInvestigations}
                onChange={(event) =>
                  setShowInvestigations(event.target.checked)
                }
              />
              Investigation locations
            </label>
            <label className="check-row">
              <input
                type="checkbox"
                checked={showAgents}
                onChange={(event) => setShowAgents(event.target.checked)}
              />
              Agent starting points
            </label>
            {showRouteLayerToggle && (
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={routesVisible}
                  onChange={(event) => toggleRoutes(event.target.checked)}
                />
                Published OSRM routes
              </label>
            )}
            <label className="check-row">
              <input
                type="checkbox"
                checked={densityVisible}
                disabled={!densityAvailable}
                onChange={(event) => toggleDensity(event.target.checked)}
              />
              H3 density overlay
            </label>
            <label className="density-resolution">
              Density resolution
              <select
                value={resolution}
                disabled={!densityAvailable}
                onChange={(event) =>
                  onResolutionChange?.(Number(event.target.value) as 7 | 8 | 9)
                }
              >
                <option value={7}>7 · broad</option>
                <option value={8}>8 · medium</option>
                <option value={9}>9 · detailed</option>
              </select>
            </label>
            {densityLoading && <small role="status">Loading H3 density…</small>}
            {densityError && (
              <small className="layer-error" role="status">
                Density unavailable. Refresh the view to retry.
              </small>
            )}
            {!densityAvailable && !densityLoading && !densityError && (
              <small>Select a service region to view H3 density.</small>
            )}
            <small>
              H3 shows location density only; it does not assign work.
            </small>
          </div>
        )}
      </div>
      {tilesFailed && (
        <div className="map-failure" role="status">
          <span>
            Map tiles are unavailable. Check the tile service or try again.
          </span>
          <button
            type="button"
            onClick={() => {
              setTilesFailed(false);
              setTileVersion((value) => value + 1);
            }}
          >
            Try again
          </button>
        </div>
      )}
      {showLegend &&
        ((showMarkerKey &&
          ((showAgents && agents.length > 0) ||
            (showInvestigations && investigations.length > 0))) ||
          (routesVisible &&
            renderRoutes.some(
              (route) => route.geometry || route.completed_geometry,
            )) ||
          showSelectedDepot) && (
          <MapLegend
            routes={routesVisible ? renderRoutes : []}
            routeStyles={lineStyles}
            showMarkerKey={showMarkerKey}
            showDepotKey={showSelectedDepot}
          />
        )}
    </div>
  );
}
