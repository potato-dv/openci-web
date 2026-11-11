import { useCallback, useMemo, useState } from "react";
import { useLocation, useSearchParams } from "react-router";
import {
  CalendarDays,
  MapPinned,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  RefreshCw,
  Route,
  UserRoundCheck,
} from "lucide-react";
import { useSession } from "@/app/session";
import {
  getPlanningReadiness,
  getPlanningDashboard,
  getPlanningMapData,
  getPlanningRouteOverview,
  retryAutomaticPlanning,
} from "@/features/route-planning/api";
import { getRegions } from "@/features/locations/api";
import { retryInvestigationRoute } from "@/features/investigations/api";
import { useResource } from "@/hooks/useResource";
import { OperationsMap } from "@/components/map/OperationsMap";
import "@/styles/planning.css";
import type { MapSelection } from "@/components/map/mapTypes";
import { RouteRosterPanel } from "@/features/route-planning/components/RouteRosterPanel";
import { PublishedRoutePanel } from "@/features/route-planning/components/PublishedRoutePanel";
import { buildPublishedRouteMapData } from "@/features/route-planning/components/publishedRouteData";
import {
  Button,
  Drawer,
  IconButton,
  InlineAlert,
  Tabs,
} from "@/components/ui/Primitives";
import { manilaToday } from "@/utils/format";
import { routeRefreshErrorCopy } from "@/utils/routeRefresh";

const routePlanningClasses = {
  canvas: "route-planning-page",
  header: "route-planning-header",
  toolbar: "route-planning-toolbar-controls",
  stats: "route-planning-stats",
  statCard: "route-planning-stat-card",
  statValue: "route-planning-stat-value",
  statLabel: "route-planning-stat-label",
  viewSwitch: "planning-view-switch route-planning-view-switch",
  workspace: "planning-workspace route-planning-workspace",
  map: "planning-map-region route-planning-map",
};

export function RoutePlanningPage() {
  const { token } = useSession();
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const regions = useResource(useCallback(() => getRegions(token), [token]));
  const workDate = params.get("date") ?? manilaToday();
  const regionCode = params.get("region") ?? "";
  const [densityResolution, setDensityResolution] = useState<7 | 8 | 9>(8);
  const mapInventory = useResource(
    useCallback(
      (signal) =>
        getPlanningMapData(token, workDate, regionCode || undefined, signal),
      [token, workDate, regionCode],
    ),
    { resourceKeys: ["route.planning"] },
  );
  const routeOverview = useResource(
    useCallback(
      (signal) =>
        getPlanningRouteOverview(
          token,
          workDate,
          regionCode || undefined,
          signal,
        ),
      [token, workDate, regionCode],
    ),
    { resourceKeys: ["route.planning"] },
  );
  const dashboard = useResource(
    useCallback(
      (signal) =>
        getPlanningDashboard(token, workDate, regionCode || undefined, signal),
      [token, workDate, regionCode],
    ),
    { resourceKeys: ["route.planning", "dashboard.route"] },
  );
  const densityResource = useResource(
    useCallback(
      (signal) =>
        regionCode
          ? getPlanningReadiness(
              token,
              workDate,
              regionCode,
              densityResolution,
              signal,
            )
          : Promise.resolve(null),
      [token, workDate, regionCode, densityResolution],
    ),
    {
      resourceKeys: ["route.readiness"],
      refetchOnFocus: true,
      refetchOnReconnect: true,
      staleTimeMs: 30_000,
    },
  );
  const [mapSearchSlot, setMapSearchSlot] = useState<HTMLDivElement | null>(
    null,
  );
  const [selectionState, setSelectionState] = useState<{
    locationKey: string;
    selection: MapSelection;
  }>(() => ({ locationKey: location.key, selection: null }));
  const selection =
    selectionState.locationKey === location.key
      ? selectionState.selection
      : null;
  const [routesVisible, setRoutesVisible] = useState(true);
  const [tab, setTab] = useState("map");
  const [drawer, setDrawer] = useState<"records" | "routes" | null>(null);
  const [leftCollapsed, setLeftCollapsed] = useState(
    () =>
      typeof window !== "undefined" &&
      window.innerWidth >= 768 &&
      window.innerWidth < 1200,
  );
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const [retryingAgentId, setRetryingAgentId] = useState<number | null>(null);
  const [retryError, setRetryError] = useState("");
  const [retryingPlanningId, setRetryingPlanningId] = useState<number | null>(
    null,
  );
  const [showDensity, setShowDensity] = useState(false);
  const regionLabels = useMemo(
    () => new Map(regions.data?.map((item) => [item.code, item.name]) ?? []),
    [regions.data],
  );
  const inventoryForScope =
    mapInventory.data?.work_date === workDate &&
    mapInventory.data.region_code === (regionCode || null)
      ? mapInventory.data
      : null;
  const routesForScope =
    routeOverview.data?.work_date === workDate &&
    routeOverview.data.region_code === (regionCode || null)
      ? routeOverview.data
      : null;
  const dashboardForScope =
    dashboard.data?.work_date === workDate &&
    dashboard.data.region_code === (regionCode || null)
      ? dashboard.data
      : null;
  const densityForScope =
    densityResource.data?.work_date === workDate &&
    densityResource.data.region_code === regionCode &&
    densityResource.data.resolution === densityResolution
      ? densityResource.data
      : null;
  const mapData = useMemo(
    () =>
      buildPublishedRouteMapData(
        inventoryForScope,
        routesForScope,
        regionLabels,
        dashboardForScope,
      ),
    [dashboardForScope, inventoryForScope, regionLabels, routesForScope],
  );
  const agents = mapData.agents;
  const investigations = mapData.investigations;
  const selectionIsInScope =
    selection === null
      ? true
      : selection.type === "agent"
        ? Boolean(
            routesForScope?.agents.some((agent) => agent.id === selection.id),
          )
        : Boolean(
            inventoryForScope?.investigations.some(
              (investigation) => investigation.id === selection.id,
            ) ||
            inventoryForScope?.unlocated_investigations.some(
              (investigation) => investigation.id === selection.id,
            ),
          );
  const selectionForScope = selectionIsInScope ? selection : null;
  const selectedAgentId =
    selectionForScope?.type === "agent"
      ? selectionForScope.id
      : selectionForScope?.type === "investigation"
        ? (investigations.find((item) => item.id === selectionForScope.id)
            ?.agent_id ?? null)
        : null;
  const routeFitRequest = useMemo(
    () =>
      routesForScope && inventoryForScope
        ? {
            key: `${workDate}|${regionCode}|${routesVisible ? "visible" : "hidden"}|${selectedAgentId ?? "all"}`,
            agentId: selectedAgentId,
          }
        : null,
    [
      inventoryForScope,
      regionCode,
      routesForScope,
      routesVisible,
      selectedAgentId,
      workDate,
    ],
  );
  const publishedCount = dashboardForScope?.published_routes ?? 0;
  const mappedCount = investigations.length;
  const availableAgentCount = dashboardForScope?.available_agents ?? 0;
  const activeAgentCount = dashboardForScope?.active_agents ?? 0;
  const scopeLabel = regionCode
    ? (regionLabels.get(regionCode) ?? "Selected region")
    : "All service regions";

  function updateScope(key: "date" | "region", value: string) {
    const next = new URLSearchParams(params);
    next.delete("run");
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
    setSelection(null);
  }

  function setSelection(next: MapSelection) {
    setSelectionState({ locationKey: location.key, selection: next });
  }

  function select(next: MapSelection) {
    setSelection(next);
    setRightCollapsed(false);
    if (window.innerWidth < 1440) {
      if (next?.type === "agent") {
        setTab("map");
        setDrawer(null);
      } else if (next) {
        setTab("routes");
        if (window.innerWidth >= 768) setDrawer("routes");
      } else {
        setTab("map");
        setDrawer(null);
      }
    }
  }

  function toggleRoutes() {
    const showAllRoutes = !routesVisible;
    if (showAllRoutes) select(null);
    setRoutesVisible(showAllRoutes);
  }

  function refreshAll() {
    mapInventory.refresh();
    routeOverview.refresh();
    dashboard.refresh();
    densityResource.refresh();
    regions.refresh();
  }

  async function retryRoute(agentId: number) {
    const agent = routesForScope?.agents.find((item) => item.id === agentId);
    if (!agent?.refresh_investigation_id || retryingAgentId != null) return;
    setRetryError("");
    setRetryingAgentId(agentId);
    try {
      await retryInvestigationRoute(token, agent.refresh_investigation_id);
      refreshAll();
    } catch (error) {
      setRetryError(
        routeRefreshErrorCopy(
          error instanceof Error
            ? error.message
            : "route_refresh_could_not_be_queued",
        ),
      );
    } finally {
      setRetryingAgentId(null);
    }
  }

  async function retryPlanning(investigationId: number) {
    if (retryingPlanningId != null) return;
    setRetryError("");
    setRetryingPlanningId(investigationId);
    try {
      await retryAutomaticPlanning(token, investigationId, workDate);
      refreshAll();
    } catch (error) {
      setRetryError(
        error instanceof Error
          ? error.message
          : "Automatic planning could not be retried.",
      );
    } finally {
      setRetryingPlanningId(null);
    }
  }

  const recordsPanel = (
    <RouteRosterPanel
      agents={agents}
      investigations={investigations}
      issues={inventoryForScope}
      routeAgents={routesForScope?.agents ?? []}
      selection={selectionForScope}
      date={workDate}
      loading={mapInventory.loading}
      onSelect={select}
    />
  );
  const routePanel = (
    <PublishedRoutePanel
      agents={routesForScope?.agents ?? []}
      investigations={investigations}
      unlocatedInvestigations={
        inventoryForScope?.unlocated_investigations ?? []
      }
      selection={selectionForScope}
      date={workDate}
      scopeLabel={scopeLabel}
      routesVisible={routesVisible}
      loading={routeOverview.loading && !routesForScope}
      retryingAgentId={retryingAgentId}
      onRetry={(agent) => void retryRoute(agent.id)}
      retryingPlanningId={retryingPlanningId}
      onRetryPlanning={(item) => void retryPlanning(item.id)}
      onSelect={select}
    />
  );
  const overviewMessage =
    routeOverview.loading && !routesForScope
      ? "Loading published routes…"
      : dashboard.loading && !dashboardForScope
        ? "Loading live assignment status…"
        : null;
  const statItems = [
    {
      label: "Total investigations",
      value: dashboardForScope ? dashboardForScope.total_investigations : "—",
      Icon: MapPinned,
    },
    {
      label: "Automatically assigned",
      value: dashboardForScope ? dashboardForScope.automatically_assigned : "—",
      Icon: UserRoundCheck,
    },
    {
      label: "Unassigned",
      value: dashboardForScope
        ? dashboardForScope.unassigned_investigations
        : "—",
      Icon: MapPinned,
    },
    {
      label: "Agents available",
      value: dashboardForScope
        ? `${availableAgentCount}/${activeAgentCount}`
        : "—",
      Icon: UserRoundCheck,
    },
    {
      label: "Published routes",
      value: dashboardForScope ? publishedCount : "—",
      Icon: Route,
    },
  ];
  const leftPanelClass = `planning-left route-planning-panel route-planning-left ${leftCollapsed ? "is-collapsed" : ""}`;
  const rightPanelClass = `planning-right route-planning-panel route-planning-right ${rightCollapsed ? "is-collapsed" : ""}`;

  return (
    <div className={routePlanningClasses.canvas}>
      <header className={routePlanningClasses.header}>
        <div className="route-planning-heading">
          <IconButton
            className="route-planning-panel-toggle route-planning-left-toggle"
            label={
              leftCollapsed
                ? "Expand agent and investigation list"
                : "Collapse agent and investigation list"
            }
            aria-expanded={!leftCollapsed}
            onClick={() => setLeftCollapsed((value) => !value)}
          >
            {leftCollapsed ? (
              <PanelLeftOpen size={18} />
            ) : (
              <PanelLeftClose size={18} />
            )}
          </IconButton>
          <div className="route-planning-title">
            <h1>Route Planning</h1>
          </div>
        </div>
        <div
          className={routePlanningClasses.toolbar}
          role="group"
          aria-label="Planning controls"
        >
          <label className="route-scope-field">
            <span className="inline-flex items-center gap-1.5">
              <CalendarDays size={15} aria-hidden="true" /> Work date
            </span>
            <input
              className="route-scope-control"
              type="date"
              aria-label="Work date"
              value={workDate}
              onChange={(event) => updateScope("date", event.target.value)}
            />
          </label>
          <label className="route-scope-field region-scope-field">
            <span className="inline-flex items-center gap-1.5">
              <MapPinned size={15} aria-hidden="true" /> Service region{" "}
              <em>Optional</em>
            </span>
            <select
              className="route-scope-control"
              aria-label="Service region (optional)"
              value={regionCode}
              onChange={(event) => updateScope("region", event.target.value)}
            >
              <option value="">All service regions</option>
              {regions.data?.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <Button
            className="route-visibility-button"
            variant="secondary"
            aria-pressed={routesVisible}
            onClick={toggleRoutes}
          >
            <Route size={15} aria-hidden="true" />
            {routesVisible ? "Hide All Routes" : "Show All Routes"}
          </Button>
          <Button
            className="route-refresh-button"
            onClick={refreshAll}
            disabled={mapInventory.loading || routeOverview.loading}
          >
            <RefreshCw size={15} aria-hidden="true" />
            Refresh view
          </Button>
          <div ref={setMapSearchSlot} className="route-planning-search-slot" />
        </div>
      </header>

      {(mapInventory.error ||
        routeOverview.error ||
        dashboard.error ||
        regions.error ||
        retryError) && (
        <div className="route-planning-error">
          <InlineAlert onRetry={refreshAll}>
            {retryError ||
              mapInventory.error ||
              routeOverview.error ||
              dashboard.error ||
              regions.error}
          </InlineAlert>
        </div>
      )}

      <div
        className={routePlanningClasses.stats}
        aria-label="Route planning counts"
        role="group"
      >
        {statItems.map(({ label, value, Icon }) => (
          <div className={routePlanningClasses.statCard} key={label}>
            <Icon
              className="route-planning-stat-icon"
              size={16}
              aria-hidden="true"
            />
            <strong className={routePlanningClasses.statValue}>{value}</strong>
            <span className={routePlanningClasses.statLabel}>{label}</span>
          </div>
        ))}
        {overviewMessage && (
          <span className="route-planning-live-status" role="status">
            {overviewMessage}
          </span>
        )}
      </div>

      <div className={routePlanningClasses.viewSwitch}>
        <Tabs
          label="Route workspace"
          value={tab}
          onChange={setTab}
          items={[
            { value: "records", label: "Records" },
            { value: "map", label: "Map" },
            { value: "routes", label: "Routes" },
          ]}
        />
        <div className="tablet-panel-actions">
          <Button onClick={() => setDrawer("records")}>Open record list</Button>
          <Button className="min-h-11!" onClick={() => setDrawer("routes")}>
            Route details
          </Button>
        </div>
        <div className="planning-desktop-drawer">
          <Button onClick={() => setDrawer("routes")}>
            Open route details
          </Button>
        </div>
        <span>
          {scopeLabel} ·{" "}
          {inventoryForScope
            ? `${mappedCount} mapped investigations`
            : "Loading records…"}
        </span>
      </div>

      <div
        className={`planning-workspace tab-${tab} ${routePlanningClasses.workspace} ${leftCollapsed ? "left-collapsed" : ""} ${rightCollapsed ? "right-collapsed" : ""}`}
      >
        <aside className={leftPanelClass}>
          {!leftCollapsed && recordsPanel}
        </aside>
        <section
          className={routePlanningClasses.map}
          aria-label="Automatic route map"
        >
          <OperationsMap
            token={token}
            searchTarget={mapSearchSlot}
            showLegend
            showMarkerKey={false}
            routeVisibility={routesVisible}
            onRouteVisibilityChange={setRoutesVisible}
            showRouteLayerToggle={false}
            routeFitRequest={routeFitRequest}
            clearSelectionOnBackgroundClick
            agents={agents}
            investigations={investigations}
            routes={mapData.routes}
            density={densityForScope?.density ?? []}
            densityLoading={densityResource.loading}
            densityError={densityResource.error}
            showDensity={showDensity}
            onDensityChange={setShowDensity}
            resolution={densityResolution}
            onResolutionChange={setDensityResolution}
            densityAvailable={Boolean(regionCode && densityForScope)}
            selection={selectionForScope}
            onSelect={select}
          />
        </section>
        <aside className={rightPanelClass}>
          <IconButton
            className="z-20!"
            label={
              rightCollapsed ? "Expand route details" : "Collapse route details"
            }
            aria-expanded={!rightCollapsed}
            onClick={() => setRightCollapsed((value) => !value)}
          >
            {rightCollapsed ? (
              <PanelRightOpen size={18} />
            ) : (
              <PanelRightClose size={18} />
            )}
          </IconButton>
          {!rightCollapsed && routePanel}
        </aside>
      </div>

      <Drawer
        title={drawer === "records" ? "Planning records" : "Route details"}
        open={Boolean(drawer)}
        onClose={() => setDrawer(null)}
      >
        {drawer === "records" ? recordsPanel : routePanel}
      </Drawer>
    </div>
  );
}
