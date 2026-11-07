import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router";
import {
  CalendarDays,
  ChevronRight,
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
  canvas: [
    "route-planning-page relative min-h-0 min-w-0 bg-[#e8ecea]",
    "min-[1440px]:h-[calc(100dvh_-_var(--height-header))]! min-[1440px]:overflow-hidden!",
  ].join(" "),
  header: [
    "route-planning-header z-[1400] flex flex-col gap-3 border-b border-openci-border bg-white px-4 py-3",
    "xl:flex-row xl:flex-wrap xl:items-end xl:justify-between xl:gap-4",
    "min-[1440px]:absolute! min-[1440px]:left-3! min-[1440px]:right-auto! min-[1440px]:top-3! min-[1440px]:w-max! min-[1440px]:max-w-[calc(100%-1.5rem)]! min-[1440px]:min-h-14! min-[1440px]:flex-nowrap! min-[1440px]:items-center! min-[1440px]:justify-start! min-[1440px]:rounded-xl! min-[1440px]:border-0! min-[1440px]:px-3! min-[1440px]:py-2! min-[1440px]:shadow-md!",
  ].join(" "),
  toolbar: [
    "route-planning-toolbar-controls flex w-full min-w-0 flex-wrap items-end gap-2 md:flex-none xl:flex-[2_1_480px]",
    "min-[1440px]:w-auto! min-[1440px]:flex-nowrap! min-[1440px]:flex-none!",
  ].join(" "),
  stats: [
    "route-planning-stats grid grid-cols-2 gap-2 px-3 py-2 sm:grid-cols-3 xl:grid-cols-4",
    "min-[1440px]:absolute! min-[1440px]:inset-x-3.5! min-[1440px]:top-24! min-[1440px]:z-[1350]! min-[1440px]:grid-cols-7! min-[1440px]:gap-1.5! min-[1440px]:min-h-0! min-[1440px]:border-0! min-[1440px]:bg-transparent! min-[1440px]:p-0!",
  ].join(" "),
  statCard: [
    "flex min-h-11 min-w-0 items-center gap-2 rounded-lg border border-openci-border bg-white px-2.5 py-2",
    "min-[1440px]:min-h-[50px]!",
  ].join(" "),
  statValue: "shrink-0 text-sm font-semibold tabular-nums",
  statLabel: "min-w-0 text-xs leading-tight text-openci-text-muted",
  viewSwitch: "planning-view-switch min-[1440px]:hidden!",
  workspace: [
    "relative min-[1440px]:absolute! min-[1440px]:inset-0! min-[1440px]:z-[1]! min-[1440px]:block! min-[1440px]:h-auto! min-[1440px]:min-h-0! min-[1440px]:w-full! min-[1440px]:overflow-hidden! min-[1440px]:bg-transparent!",
  ].join(" "),
  widePanel: [
    "min-[1440px]:absolute! min-[1440px]:top-[208px]! min-[1440px]:bottom-[76px]! min-[1440px]:z-[1200]! min-[1440px]:block! min-[1440px]:overflow-x-hidden! min-[1440px]:overflow-y-auto! min-[1440px]:rounded-xl! min-[1440px]:border-0! min-[1440px]:bg-white! min-[1440px]:shadow-md!",
  ].join(" "),
  map: [
    "planning-map-region relative isolate min-[1440px]:absolute! min-[1440px]:inset-0! min-[1440px]:z-0! min-[1440px]:block! min-[1440px]:h-full! min-[1440px]:w-full! min-[1440px]:min-w-0!",
    "min-[1440px]:[&_.operations-map]:absolute! min-[1440px]:[&_.operations-map]:inset-0! min-[1440px]:[&_.operations-map]:h-full! min-[1440px]:[&_.operations-map]:w-full! min-[1440px]:[&_.operations-map]:min-h-0! min-[1440px]:[&_.operations-map]:flex-none!",
    "min-[1440px]:[&_.map-zoom-controls]:top-auto! min-[1440px]:[&_.map-zoom-controls]:bottom-3! min-[1440px]:[&_.map-zoom-controls]:left-3! min-[1440px]:[&_.map-zoom-controls]:z-[1000]!",
    "min-[1440px]:[&_.map-fit-controls]:top-auto! min-[1440px]:[&_.map-fit-controls]:bottom-3! min-[1440px]:[&_.map-fit-controls]:left-16! min-[1440px]:[&_.map-fit-controls]:z-[1000]! min-[1440px]:[&_.map-fit-controls]:flex!",
    "min-[1440px]:[&_.map-layer-control]:top-auto! min-[1440px]:[&_.map-layer-control]:right-auto! min-[1440px]:[&_.map-layer-control]:bottom-3! min-[1440px]:[&_.map-layer-control]:left-[200px]! min-[1440px]:[&_.map-layer-control]:z-[1000]!",
    "min-[1440px]:[&_.layer-menu]:top-auto! min-[1440px]:[&_.layer-menu]:right-auto! min-[1440px]:[&_.layer-menu]:bottom-11! min-[1440px]:[&_.layer-menu]:left-0!",
  ].join(" "),
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
  );
  const dashboard = useResource(
    useCallback(
      (signal) =>
        getPlanningDashboard(token, workDate, regionCode || undefined, signal),
      [token, workDate, regionCode],
    ),
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
  const optimizingCount = dashboardForScope?.optimizing_routes ?? 0;
  const mappedCount = investigations.length;
  const availableAgentCount = dashboardForScope?.available_agents ?? 0;
  const activeAgentCount = dashboardForScope?.active_agents ?? 0;
  const hasQueuedRefresh =
    optimizingCount > 0 ||
    (routesForScope?.agents.some(
      (agent) =>
        agent.route_status === "queued" ||
        agent.route_status === "running" ||
        agent.planning_status === "queued" ||
        agent.planning_status === "running",
    ) ??
      false);
  const hasStaleRoute =
    routesForScope?.agents.some(
      (agent) =>
        agent.route_status === "needs_refresh" ||
        agent.route_status === "failed",
    ) ?? false;
  const refreshMapData = mapInventory.refresh;
  const refreshRouteData = routeOverview.refresh;
  const refreshDashboard = dashboard.refresh;
  const scopeLabel = regionCode
    ? (regionLabels.get(regionCode) ?? "Selected region")
    : "All service regions";

  useEffect(() => {
    const timer = window.setInterval(
      () => {
        refreshRouteData();
        if (hasQueuedRefresh || hasStaleRoute) {
          refreshMapData();
          refreshDashboard();
        }
      },
      hasQueuedRefresh ? 2500 : 10000,
    );
    return () => window.clearInterval(timer);
  }, [
    hasQueuedRefresh,
    hasStaleRoute,
    refreshDashboard,
    refreshMapData,
    refreshRouteData,
  ]);

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
      headerAction={
        <IconButton
          className="hidden! h-8! w-8! shrink-0 min-[1440px]:grid!"
          label="Collapse agent and investigation list"
          aria-expanded="true"
          onClick={() => setLeftCollapsed(true)}
        >
          <PanelLeftClose size={18} />
        </IconButton>
      }
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
  const leftPanelClass = [
    "planning-left",
    routePlanningClasses.widePanel,
    "min-[1440px]:left-3.5!",
    leftCollapsed
      ? "min-[1440px]:top-[208px]! min-[1440px]:bottom-auto! min-[1440px]:h-11! min-[1440px]:w-11! min-[1440px]:overflow-hidden!"
      : "min-[1440px]:w-[304px]!",
  ]
    .filter(Boolean)
    .join(" ");
  const rightPanelClass = [
    "planning-right",
    routePlanningClasses.widePanel,
    "min-[1440px]:right-3.5!",
    rightCollapsed
      ? "min-[1440px]:top-[208px]! min-[1440px]:bottom-auto! min-[1440px]:h-11! min-[1440px]:w-11! min-[1440px]:overflow-hidden!"
      : "min-[1440px]:w-[344px]!",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={routePlanningClasses.canvas}>
      <header className={routePlanningClasses.header}>
        <div className="route-planning-heading flex min-w-0 flex-col gap-1 md:w-full md:flex-none xl:w-auto xl:min-w-max xl:flex-none min-[1440px]:min-w-[220px]! min-[1440px]:flex-none!">
          <nav
            className="route-planning-breadcrumb flex items-center gap-1.5 whitespace-nowrap text-xs text-openci-text-muted"
            aria-label="Breadcrumb"
          >
            <Link
              className="text-openci-accent-strong no-underline"
              to="/dashboard"
            >
              Collector
            </Link>
            <ChevronRight size={14} aria-hidden="true" />
            <span aria-current="page">Route Planning</span>
          </nav>
          <h1 className="m-0! text-[24px]! font-semibold! leading-tight! tracking-[-0.025em]!">
            Route Planning
          </h1>
        </div>
        <div className={routePlanningClasses.toolbar}>
          <label className="route-scope-field flex min-w-[150px] flex-1 flex-col gap-1 text-[13px] font-medium text-openci-text-muted min-[1440px]:flex-none!">
            <span className="inline-flex items-center gap-1.5">
              <CalendarDays size={15} aria-hidden="true" /> Work date
            </span>
            <input
              className="h-9 min-h-9! w-full rounded-md px-2.5 py-1.5 text-sm min-[1440px]:w-40!"
              type="date"
              aria-label="Work date"
              value={workDate}
              onChange={(event) => updateScope("date", event.target.value)}
            />
          </label>
          <label className="route-scope-field region-scope-field flex min-w-[180px] flex-[1.25] flex-col gap-1 text-[13px] font-medium text-openci-text-muted min-[1440px]:flex-none!">
            <span className="inline-flex items-center gap-1.5">
              <MapPinned size={15} aria-hidden="true" /> Service region{" "}
              <em className="font-normal not-italic text-openci-text-subtle">
                Optional
              </em>
            </span>
            <select
              className="h-9 min-h-9! w-full px-2.5 py-1.5 text-sm min-[1440px]:w-52!"
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
            className="route-visibility-button min-h-9! shrink-0 whitespace-nowrap"
            variant="secondary"
            aria-pressed={routesVisible}
            onClick={toggleRoutes}
          >
            <Route size={15} aria-hidden="true" />
            {routesVisible ? "Hide All Routes" : "Show All Routes"}
          </Button>
          <Button
            className="route-refresh-button min-h-9! shrink-0 whitespace-nowrap"
            onClick={refreshAll}
            disabled={mapInventory.loading || routeOverview.loading}
          >
            <RefreshCw size={15} aria-hidden="true" />
            Refresh view
          </Button>
          <div
            ref={setMapSearchSlot}
            className="route-planning-search-slot w-full min-w-0 xl:max-w-[320px] min-[1440px]:w-[300px]! min-[1440px]:flex-none! min-[1600px]:w-[340px]!"
          />
        </div>
      </header>

      {(mapInventory.error ||
        routeOverview.error ||
        dashboard.error ||
        regions.error ||
        retryError) && (
        <div className="route-planning-error mx-3 my-2 rounded-lg border border-openci-danger-border bg-openci-danger-surface px-3 py-2 min-[1440px]:absolute! min-[1440px]:left-1/2! min-[1440px]:top-44! min-[1440px]:z-[1600]! min-[1440px]:w-[min(560px,calc(100%-2rem))]! min-[1440px]:-translate-x-1/2!">
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
              className="shrink-0 text-openci-accent"
              size={16}
              aria-hidden="true"
            />
            <strong className={routePlanningClasses.statValue}>{value}</strong>
            <span className={routePlanningClasses.statLabel}>{label}</span>
          </div>
        ))}
        {overviewMessage && (
          <span
            className="route-planning-live-status col-span-full min-h-6 justify-self-start rounded-full border border-openci-border bg-white px-2.5 py-1 text-xs text-openci-text-muted min-[1440px]:mx-0!"
            role="status"
          >
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
        <div className="tablet-panel-actions min-[1440px]:hidden!">
          <Button className="min-h-11!" onClick={() => setDrawer("records")}>
            Open record list
          </Button>
          <Button className="min-h-11!" onClick={() => setDrawer("routes")}>
            Route details
          </Button>
        </div>
        <div className="planning-desktop-drawer min-[1440px]:hidden!">
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
          {leftCollapsed ? (
            <IconButton
              className="z-20!"
              label="Expand agent and investigation list"
              aria-expanded="false"
              onClick={() => setLeftCollapsed(false)}
            >
              <PanelLeftOpen size={18} />
            </IconButton>
          ) : (
            recordsPanel
          )}
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
