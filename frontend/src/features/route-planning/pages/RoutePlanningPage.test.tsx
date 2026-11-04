import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SessionContext } from "@/app/session";
import type {
  PlanningDashboard,
  PlanningMapData,
  PlanningRouteOverview,
} from "@/types/api";
import type { MapSelection } from "@/components/map/mapTypes";
import { RoutePlanningPage } from "./RoutePlanningPage";

const api = vi.hoisted(() => ({
  getRegions: vi.fn(),
  getPlanningMapData: vi.fn(),
  getPlanningRouteOverview: vi.fn(),
  getPlanningDashboard: vi.fn(),
  getPlanningReadiness: vi.fn(),
  retryAutomaticPlanning: vi.fn(),
  retryInvestigationRoute: vi.fn(),
}));

vi.mock("@/features/locations/api", () => ({
  getRegions: api.getRegions,
}));
vi.mock("@/features/route-planning/api", () => ({
  getPlanningMapData: api.getPlanningMapData,
  getPlanningRouteOverview: api.getPlanningRouteOverview,
  getPlanningDashboard: api.getPlanningDashboard,
  getPlanningReadiness: api.getPlanningReadiness,
  retryAutomaticPlanning: api.retryAutomaticPlanning,
}));
vi.mock("@/features/investigations/api", () => ({
  retryInvestigationRoute: api.retryInvestigationRoute,
}));
vi.mock("@/components/map/OperationsMap", () => ({
  OperationsMap: (props: {
    routeVisibility?: boolean;
    routes?: { agent_id: number }[];
    agents?: unknown[];
    investigations?: { id: number; agent_id: number | null }[];
    selection?: MapSelection;
    onSelect?: (selection: MapSelection) => void;
  }) => {
    const selectedAgentId =
      props.selection?.type === "agent"
        ? props.selection.id
        : props.selection?.type === "investigation"
          ? (props.investigations?.find(
              (investigation) => investigation.id === props.selection?.id,
            )?.agent_id ?? null)
          : null;
    const focusedRoutes = props.selection
      ? selectedAgentId == null
        ? []
        : (props.routes ?? []).filter(
            (route) => route.agent_id === selectedAgentId,
          )
      : (props.routes ?? []);
    return (
      <div
        data-testid="operations-map"
        data-routes-visible={String(props.routeVisibility)}
        data-selection={
          props.selection
            ? `${props.selection.type}:${props.selection.id}`
            : "none"
        }
        data-visible-route-ids={
          props.routeVisibility
            ? focusedRoutes.map((route) => route.agent_id).join(",")
            : ""
        }
        data-agent-marker-count={props.agents?.length ?? 0}
        data-investigation-marker-count={props.investigations?.length ?? 0}
      >
        <button
          type="button"
          onClick={() => props.onSelect?.({ type: "agent", id: 7 })}
        >
          Test map agent 7
        </button>
        <button
          type="button"
          onClick={() => props.onSelect?.({ type: "agent", id: 8 })}
        >
          Test map agent 8
        </button>
        <button
          type="button"
          onClick={() => props.onSelect?.({ type: "investigation", id: 11 })}
        >
          Test map investigation 11
        </button>
        <button type="button" onClick={() => props.onSelect?.(null)}>
          Test map background
        </button>
      </div>
    );
  },
}));

const mapData = {
  work_date: "2026-10-23",
  region_code: null,
  agents: [
    {
      id: 7,
      name: "Avery Santos",
      is_active: true,
      region_code: "1300000000",
      is_available: true,
      shift_starts_at: "2026-10-23T00:00:00Z",
      shift_ends_at: "2026-10-23T09:00:00Z",
      start: { latitude: 14.6, longitude: 121, label: "Office" },
    },
  ],
  investigations: [
    {
      id: 11,
      reference_number: "INV-0011",
      address_display: "12 Example Street",
      latitude: 14.65,
      longitude: 121.05,
      priority: "high",
      status: "assigned",
      region_code: "1300000000",
      assigned_agent_id: 7,
      assigned_agent_name: "Avery Santos",
      service_duration_seconds: 1800,
      visit_not_before_at: null,
      visit_due_at: null,
    },
  ],
  unlocated_investigations: [],
  unlocated_agents: [],
} as PlanningMapData;

const routeData = {
  work_date: "2026-10-23",
  region_code: null,
  agents: [
    {
      id: 7,
      name: "Avery Santos",
      is_active: true,
      region_code: "1300000000",
      shift: {
        id: 17,
        agent_id: 7,
        work_date: "2026-10-23",
        region_code: "1300000000",
        is_available: true,
        shift_starts_at: "2026-10-23T00:00:00Z",
        shift_ends_at: "2026-10-23T09:00:00Z",
        start_latitude: 14.6,
        start_longitude: 121,
        end_latitude: null,
        end_longitude: null,
        start_location_label: "Office",
        start_location_source: "manual",
        start_location_provider_ref: null,
        end_location_label: null,
        end_location_source: null,
        end_location_provider_ref: null,
        max_visits: 8,
        max_open_cases: 20,
        current_planning_run_id: 21,
      },
      route_status: "published",
      refresh_errors: [],
      priority_order_warnings: [
        {
          investigation_id: 11,
          reference_number: "INV-0011",
          deferred_investigation_id: 12,
          deferred_reference_number: "INV-0012",
          reason: "schedule_constraint",
        },
        {
          investigation_id: null,
          reference_number: null,
          deferred_investigation_id: null,
          deferred_reference_number: null,
          reason: "search_limit",
        },
      ],
      refresh_investigation_id: 11,
      run_id: 21,
      planning_status: "idle",
      planning_error_code: null,
      planning_run_id: 21,
      open_case_count: 1,
      remaining_open_capacity: 19,
      route: {
        agent_id: 7,
        agent_name: "Avery Santos",
        geometry_status: "ready",
        geometry_error_code: null,
        geometry: {
          type: "LineString",
          coordinates: [
            [121, 14.6],
            [121.05, 14.65],
          ],
        },
        geometry_digest: "digest",
        total_distance_metres: 15196,
        total_travel_seconds: 1069,
        total_waiting_seconds: 0,
        total_planned_waiting_seconds: 0,
        planned_departure_at: "2026-10-23T02:42:11Z",
        start: { latitude: 14.6, longitude: 121, label: "Office" },
        end: null,
      },
      stops: [
        {
          service_duration_seconds: 1800,
          investigation_id: 11,
          reference_number: "INV-0011",
          address_display: "12 Example Street",
          sequence: 1,
          estimated_arrival_at: "2026-10-23T01:22:22Z",
          earliest_arrival_estimate_at: "2026-10-23T01:22:22Z",
          planned_arrival_at: "2026-10-23T03:00:00Z",
          estimated_service_start_at: "2026-10-23T03:00:00Z",
          waiting_seconds: 0,
          planned_waiting_seconds: 0,
          travel_seconds: 1069,
          travel_metres: 15196,
          latitude: 14.65,
          longitude: 121.05,
          priority: "high",
          status: "assigned",
        },
      ],
    },
  ],
} as PlanningRouteOverview;

const dashboardData: PlanningDashboard = {
  work_date: "2026-10-23",
  region_code: null,
  total_investigations: 1,
  automatically_assigned: 1,
  unassigned_investigations: 0,
  active_agents: 2,
  available_agents: 1,
  optimizing_routes: 0,
  published_routes: 1,
  failed_planning_jobs: 0,
  investigation_states: [
    {
      investigation_id: 11,
      planning_status: "assigned",
      reason: null,
      planning_run_id: 21,
      assignment_source: "automatic",
    },
  ],
};

describe("RoutePlanningPage", () => {
  beforeEach(() => {
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: 1440,
    });
    api.getRegions.mockResolvedValue([
      { code: "1300000000", name: "Metro Manila" },
    ]);
    api.getPlanningMapData.mockResolvedValue(mapData);
    api.getPlanningRouteOverview.mockResolvedValue(routeData);
    api.getPlanningDashboard.mockResolvedValue(dashboardData);
    api.getPlanningReadiness.mockResolvedValue(null);
    api.retryAutomaticPlanning.mockResolvedValue({});
    api.retryInvestigationRoute.mockResolvedValue({});
  });

  it("shows every scoped route when routes are shown and restores focus on selection", async () => {
    const secondMapAgent = {
      ...mapData.agents[0],
      id: 8,
      name: "Jordan Lee",
      start: {
        latitude: 14.7,
        longitude: 121.2,
        label: "North Depot",
      },
    };
    const secondRouteAgent = {
      ...routeData.agents[0],
      id: 8,
      name: "Jordan Lee",
      shift: {
        ...routeData.agents[0].shift,
        id: 18,
        agent_id: 8,
      },
      route: {
        ...routeData.agents[0].route!,
        agent_id: 8,
        agent_name: "Jordan Lee",
        geometry: {
          type: "LineString" as const,
          coordinates: [
            [121.2, 14.7],
            [121.25, 14.75],
          ],
        },
      },
      stops: [],
    };
    api.getPlanningMapData.mockResolvedValue({
      ...mapData,
      agents: [...mapData.agents, secondMapAgent],
    });
    api.getPlanningRouteOverview.mockResolvedValue({
      ...routeData,
      agents: [...routeData.agents, secondRouteAgent],
    });

    render(
      <MemoryRouter initialEntries={["/route-planning?date=2026-10-23"]}>
        <SessionContext.Provider
          value={{
            token: "test-token",
            user: {
              id: 1,
              name: "Supervisor",
              email: "supervisor@example.test",
              role: "supervisor",
              is_active: true,
            },
            logout() {},
          }}
        >
          <RoutePlanningPage />
        </SessionContext.Provider>
      </MemoryRouter>,
    );

    const map = await screen.findByTestId("operations-map");
    await waitFor(() =>
      expect(map).toHaveAttribute("data-visible-route-ids", "7,8"),
    );

    fireEvent.click(screen.getByRole("button", { name: "Test map agent 7" }));
    expect(map).toHaveAttribute("data-selection", "agent:7");
    expect(map).toHaveAttribute("data-visible-route-ids", "7");
    fireEvent.click(screen.getByRole("button", { name: "Test map agent 8" }));
    expect(map).toHaveAttribute("data-selection", "agent:8");
    expect(map).toHaveAttribute("data-visible-route-ids", "8");
    fireEvent.click(screen.getByRole("button", { name: "Hide All Routes" }));
    expect(map).toHaveAttribute("data-visible-route-ids", "");
    expect(map).toHaveAttribute("data-selection", "agent:8");
    expect(map).toHaveAttribute("data-agent-marker-count", "2");
    expect(map).toHaveAttribute("data-investigation-marker-count", "1");
    fireEvent.click(screen.getByRole("button", { name: "Show All Routes" }));
    expect(map).toHaveAttribute("data-selection", "none");
    expect(map).toHaveAttribute("data-visible-route-ids", "7,8");

    fireEvent.click(screen.getByRole("button", { name: "Test map agent 7" }));
    expect(map).toHaveAttribute("data-visible-route-ids", "7");

    fireEvent.click(screen.getByRole("button", { name: "Hide All Routes" }));
    expect(map).toHaveAttribute("data-visible-route-ids", "");
    expect(map).toHaveAttribute("data-selection", "agent:7");
    fireEvent.click(
      screen.getByRole("button", { name: "Test map background" }),
    );
    expect(map).toHaveAttribute("data-selection", "none");
    fireEvent.click(screen.getByRole("button", { name: "Show All Routes" }));
    expect(map).toHaveAttribute("data-selection", "none");
    expect(map).toHaveAttribute("data-visible-route-ids", "7,8");

    fireEvent.click(
      screen.getByRole("button", { name: "Test map investigation 11" }),
    );
    expect(map).toHaveAttribute("data-selection", "investigation:11");
    expect(map).toHaveAttribute("data-visible-route-ids", "7");
    fireEvent.click(screen.getByRole("button", { name: "Test map agent 7" }));
    expect(map).toHaveAttribute("data-selection", "agent:7");
    expect(map).toHaveAttribute("data-visible-route-ids", "7");
  });

  it("reviews assignment-generated routes without manual generation or approval actions", async () => {
    render(
      <MemoryRouter initialEntries={["/route-planning?date=2026-10-23"]}>
        <SessionContext.Provider
          value={{
            token: "test-token",
            user: {
              id: 1,
              name: "Supervisor",
              email: "supervisor@example.test",
              role: "supervisor",
              is_active: true,
            },
            logout() {},
          }}
        >
          <RoutePlanningPage />
        </SessionContext.Provider>
      </MemoryRouter>,
    );

    expect((await screen.findAllByText("INV-0011")).length).toBeGreaterThan(0);
    expect(
      await screen.findByRole("region", { name: "Route scope summary" }),
    ).toBeInTheDocument();
    const map = screen.getByTestId("operations-map");
    expect(map).toHaveAttribute("data-routes-visible", "true");
    fireEvent.click(screen.getByRole("button", { name: "Hide All Routes" }));
    expect(screen.getByRole("button", { name: "Show All Routes" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(map).toHaveAttribute("data-routes-visible", "false");
    fireEvent.click(screen.getByRole("button", { name: "Show All Routes" }));
    expect(map).toHaveAttribute("data-routes-visible", "true");
    fireEvent.click(screen.getByRole("tab", { name: /Agents/ }));
    fireEvent.click(screen.getByRole("button", { name: /Avery Santos/ }));
    expect(
      (await screen.findAllByText("Stop sequence")).length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("Priority sequencing needs review:").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/visit windows, shift hours, or a break require this order/i).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/bounded priority optimization could not confirm a fully prioritized order/i).length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("Route published").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Earliest arrival estimate · depart as soon as possible").length).toBeGreaterThan(0);
    expect(screen.getAllByText("9:22 AM").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Planned departure").length).toBeGreaterThan(0);
    expect(screen.getAllByText("10:42 AM").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Planned arrival").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Wait at stop").length).toBeGreaterThan(0);
    expect(screen.getAllByText("No scheduled wait").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Service starts").length).toBeGreaterThan(0);
    expect(screen.getAllByText("11:00 AM").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Service ends").length).toBeGreaterThan(0);
    expect(screen.getAllByText("11:30 AM").length).toBeGreaterThan(0);
    expect(screen.queryByText("1h 38m")).not.toBeInTheDocument();
    expect(screen.getAllByText("18 min · 15.2 km").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("tab", { name: /Investigations/ }));
    expect(
      screen.getByLabelText("Service region (optional)"),
    ).toBeInTheDocument();
    expect(screen.getByText("Total investigations")).toBeInTheDocument();
    expect(screen.getByText("Automatically assigned")).toBeInTheDocument();
    expect(screen.getAllByText("Unassigned").length).toBeGreaterThan(0);
    expect(screen.getByText("Published routes")).toBeInTheDocument();
    const counts = screen.getByRole("group", { name: "Route planning counts" });
    for (const label of [
      "Total investigations",
      "Automatically assigned",
      "Unassigned",
      "Agents available",
      "Routes optimizing",
      "Published routes",
      "Failed planning jobs",
    ]) {
      expect(within(counts).getByText(label)).toBeInTheDocument();
    }
    expect(
      screen.getByRole("tab", { name: /Needs confirmation/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("Filter investigations by priority"),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("Filter investigations by status"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /generate plan/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /approve assignments/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide All Routes" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Collapse agent and investigation list",
      }),
    );
    expect(
      screen.getByRole("button", {
        name: "Expand agent and investigation list",
      }),
    ).toHaveAttribute("aria-expanded", "false");
    expect(
      screen.getByRole("button", { name: "Collapse route details" }),
    ).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(
      screen.getByRole("button", {
        name: "Expand agent and investigation list",
      }),
    );
    expect(
      screen.getByRole("button", {
        name: "Collapse agent and investigation list",
      }),
    ).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(
      screen.getByRole("button", { name: "Collapse route details" }),
    );
    expect(
      screen.getByRole("button", { name: "Expand route details" }),
    ).toHaveAttribute("aria-expanded", "false");
    expect(
      screen.getByRole("button", {
        name: "Collapse agent and investigation list",
      }),
    ).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(
      screen.getByRole("button", { name: "Expand route details" }),
    );
    expect(
      screen.getByRole("button", { name: "Collapse route details" }),
    ).toHaveAttribute("aria-expanded", "true");

    fireEvent.change(screen.getByLabelText("Filter investigations by status"), {
      target: { value: "pending" },
    });
    expect(
      within(screen.getByRole("region", { name: "Investigations" })).getByText(
        "No investigations match the current search and filters.",
      ),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Hide All Routes" }));
    fireEvent.change(screen.getByLabelText("Service region (optional)"), {
      target: { value: "1300000000" },
    });
    await waitFor(() =>
      expect(api.getPlanningRouteOverview).toHaveBeenLastCalledWith(
        "test-token",
        "2026-10-23",
        "1300000000",
        expect.anything(),
      ),
    );
    expect(map).toHaveAttribute("data-selection", "none");
    expect(screen.getByRole("button", { name: "Show All Routes" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );

    fireEvent.change(screen.getByLabelText("Work date"), {
      target: { value: "2026-10-24" },
    });
    await waitFor(() =>
      expect(api.getPlanningRouteOverview).toHaveBeenLastCalledWith(
        "test-token",
        "2026-10-24",
        "1300000000",
        expect.anything(),
      ),
    );
    expect(map).toHaveAttribute("data-selection", "none");
    expect(screen.getByRole("button", { name: "Show All Routes" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("shows an optimizing investigation without presenting it as officially assigned", async () => {
    api.getPlanningDashboard.mockResolvedValue({
      ...dashboardData,
      automatically_assigned: 0,
      unassigned_investigations: 1,
      published_routes: 0,
      optimizing_routes: 1,
      investigation_states: [
        {
          investigation_id: 11,
          planning_status: "optimizing",
          reason: null,
          planning_run_id: 22,
          assignment_source: null,
        },
      ],
    });
    api.getPlanningMapData.mockResolvedValue({
      ...mapData,
      investigations: [
        {
          ...mapData.investigations[0],
          status: "pending",
          assigned_agent_id: null,
          assigned_agent_name: null,
        },
      ],
    });
    api.getPlanningRouteOverview.mockResolvedValue({
      ...routeData,
      agents: routeData.agents.map((agent) => ({
        ...agent,
        route_status: "none",
        route: null,
        stops: [],
      })),
    });

    render(
      <MemoryRouter initialEntries={["/route-planning?date=2026-10-23"]}>
        <SessionContext.Provider
          value={{
            token: "test-token",
            user: {
              id: 1,
              name: "Supervisor",
              email: "supervisor@example.test",
              role: "supervisor",
              is_active: true,
            },
            logout() {},
          }}
        >
          <RoutePlanningPage />
        </SessionContext.Provider>
      </MemoryRouter>,
    );

    expect((await screen.findAllByText("Optimizing")).length).toBeGreaterThan(
      0,
    );
    expect(screen.getAllByText("Unassigned").length).toBeGreaterThan(0);
    expect(
      screen.queryByText("Assigned to Avery Santos"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /approve assignments/i }),
    ).not.toBeInTheDocument();
    expect(
      (await screen.findAllByText(/No published routes are available for/))
        .length,
    ).toBeGreaterThan(0);
  });

  it("keeps polling route data until background planning finishes", async () => {
    api.getPlanningRouteOverview.mockResolvedValue({
      ...routeData,
      agents: routeData.agents.map((agent) => ({
        ...agent,
        route_status: "running",
        route: null,
        stops: [],
      })),
    });
    api.getPlanningDashboard.mockResolvedValue({
      ...dashboardData,
      optimizing_routes: 1,
    });
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });

    try {
      render(
        <MemoryRouter initialEntries={["/route-planning?date=2026-10-23"]}>
          <SessionContext.Provider
            value={{
              token: "test-token",
              user: {
                id: 1,
                name: "Supervisor",
                email: "supervisor@example.test",
                role: "supervisor",
                is_active: true,
              },
              logout() {},
            }}
          >
            <RoutePlanningPage />
          </SessionContext.Provider>
        </MemoryRouter>,
      );

      await screen.findByRole("region", { name: "Route scope summary" });
      const initialOverviewCalls =
        api.getPlanningRouteOverview.mock.calls.length;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2600);
      });
      await waitFor(() =>
        expect(
          api.getPlanningRouteOverview.mock.calls.length,
        ).toBeGreaterThanOrEqual(initialOverviewCalls + 1),
      );
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2600);
      });

      expect(
        api.getPlanningRouteOverview.mock.calls.length,
      ).toBeGreaterThanOrEqual(initialOverviewCalls + 2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("discovers planning that starts while the page is open", async () => {
    api.getPlanningRouteOverview
      .mockResolvedValueOnce(routeData)
      .mockResolvedValue({
        ...routeData,
        agents: routeData.agents.map((agent) => ({
          ...agent,
          route_status: "running",
          route: null,
          stops: [],
        })),
      });
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });

    try {
      render(
        <MemoryRouter initialEntries={["/route-planning?date=2026-10-23"]}>
          <SessionContext.Provider
            value={{
              token: "test-token",
              user: {
                id: 1,
                name: "Supervisor",
                email: "supervisor@example.test",
                role: "supervisor",
                is_active: true,
              },
              logout() {},
            }}
          >
            <RoutePlanningPage />
          </SessionContext.Provider>
        </MemoryRouter>,
      );

      await screen.findByRole("region", { name: "Route scope summary" });
      const initialOverviewCalls =
        api.getPlanningRouteOverview.mock.calls.length;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10000);
      });
      await waitFor(() =>
        expect(
          api.getPlanningRouteOverview.mock.calls.length,
        ).toBeGreaterThanOrEqual(initialOverviewCalls + 1),
      );

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2600);
      });
      expect(
        api.getPlanningRouteOverview.mock.calls.length,
      ).toBeGreaterThanOrEqual(initialOverviewCalls + 2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows the valid route and explains excluded assigned investigations", async () => {
    api.getPlanningRouteOverview.mockResolvedValue({
      ...routeData,
      agents: routeData.agents.map((agent) => ({
        ...agent,
        route_status: "partially_published",
        planning_warnings: [
          {
            investigation_id: 13,
            reference_number: "INV-BLOCKED",
            reason: "location_unconfirmed",
          },
        ],
      })),
    });

    render(
      <MemoryRouter initialEntries={["/route-planning?date=2026-10-23"]}>
        <SessionContext.Provider
          value={{
            token: "test-token",
            user: {
              id: 1,
              name: "Supervisor",
              email: "supervisor@example.test",
              role: "supervisor",
              is_active: true,
            },
            logout() {},
          }}
        >
          <RoutePlanningPage />
        </SessionContext.Provider>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("tab", { name: /Agents/ }));
    fireEvent.click(screen.getByRole("button", { name: /Avery Santos/ }));

    expect(
      await screen.findAllByText("Route published with blockers"),
    ).not.toHaveLength(0);
    expect(screen.getByRole("link", { name: "INV-BLOCKED" })).toHaveAttribute(
      "href",
      "/investigations/13",
    );
    expect(
      screen.getByRole("link", { name: "INV-BLOCKED" }).parentElement,
    ).toHaveTextContent("The location needs confirmation.");
  });
});
