import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SessionContext } from "@/app/session";
import type {
  PlanningDashboard,
  PlanningMapData,
  PlanningRouteOverview,
} from "@/types/api";
import { RoutePlanningPage } from "./RoutePlanningPage";

const api = vi.hoisted(() => ({
  getRegions: vi.fn(),
  getPlanningMapData: vi.fn(),
  getPlanningRouteOverview: vi.fn(),
  getPlanningDashboard: vi.fn(),
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
  retryAutomaticPlanning: api.retryAutomaticPlanning,
}));
vi.mock("@/features/investigations/api", () => ({
  retryInvestigationRoute: api.retryInvestigationRoute,
}));
vi.mock("@/components/map/OperationsMap", () => ({
  OperationsMap: () => <div aria-label="Automatic route map" />,
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
        total_distance_metres: 4500,
        total_travel_seconds: 900,
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
          estimated_arrival_at: "2026-10-23T01:30:00Z",
          travel_seconds: 900,
          travel_metres: 4500,
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
    api.retryAutomaticPlanning.mockResolvedValue({});
    api.retryInvestigationRoute.mockResolvedValue({});
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
      (await screen.findAllByText("Stop sequence")).length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("Route published").length).toBeGreaterThan(0);
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
  });
});
