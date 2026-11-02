import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import type { AgentRoute } from "@/types/api";

vi.mock("@/components/map/OperationsMap", () => ({
  OperationsMap: ({
    agents,
    investigations = [],
  }: {
    agents: { start: { label?: string; latitude: number } }[];
    investigations?: { reference_number: string }[];
  }) => (
    <div data-testid="route-map-origin">
      {agents[0].start.label} · {agents[0].start.latitude}
      {investigations.map((item) => <span key={item.reference_number}>{item.reference_number}</span>)}
    </div>
  ),
}));

import { AgentRouteView } from "./AgentRouteView";

const baseRoute: AgentRoute = {
  work_date: "2026-11-02",
  reason: "route_refresh_pending",
  shift: {
    id: 1,
    agent_id: 7,
    work_date: "2026-11-02",
    region_code: "1300000000",
    is_available: true,
    shift_starts_at: "2026-11-02T00:00:00Z",
    shift_ends_at: "2026-11-02T09:00:00Z",
    start_latitude: 14.6,
    start_longitude: 121.1,
    end_latitude: null,
    end_longitude: null,
    max_visits: 8,
    max_open_cases: 20,
    current_planning_run_id: null,
    last_completed_latitude: 14.72,
    last_completed_longitude: 121.3,
    last_completed_at: "2026-11-02T02:00:00Z",
    last_completed_investigation_id: 15,
    last_completed_report_id: 18,
  },
  route: null,
  revisit_requests: [],
  stops: [],
};

function renderRoute(data: AgentRoute) {
  return render(
    <MemoryRouter>
      <AgentRouteView data={data} agentId={7} agentName="Avery Santos" />
    </MemoryRouter>,
  );
}

describe("AgentRouteView", () => {
  it("keeps the latest submitted visit visible as an estimated origin during route refresh", () => {
    renderRoute(baseRoute);

    expect(screen.getByTestId("route-map-origin")).toHaveTextContent(
      "Latest completed visit (estimated) · 14.72",
    );
    expect(screen.getByText("Route update in progress")).toBeInTheDocument();
  });

  it("shows stop travel, arrival, waiting, service start, and service duration separately", () => {
    renderRoute({
      ...baseRoute,
      reason: null,
      route: {
        agent_id: 7,
        agent_name: "Avery Santos",
        geometry_status: "ready",
        geometry_error_code: null,
        geometry: null,
        geometry_digest: null,
        total_distance_metres: 1400,
        total_travel_seconds: 600,
        total_service_seconds: 1200,
        total_waiting_seconds: 300,
        total_break_seconds: 0,
        start: { latitude: 14.72, longitude: 121.3, label: "Latest completed visit (estimated)" },
        end: null,
      },
      stops: [
        {
          service_duration_seconds: 1200,
          investigation_id: 21,
          reference_number: "INV-0021",
          address_display: "21 Sample Road",
          sequence: 1,
          estimated_arrival_at: "2026-11-02T03:00:00Z",
          estimated_service_start_at: "2026-11-02T03:05:00Z",
          waiting_seconds: 300,
          travel_seconds: 600,
          travel_metres: 1400,
          latitude: 14.73,
          longitude: 121.31,
          priority: "normal",
          status: "assigned",
        },
      ],
    });

    for (const label of [
      "Travel from previous stop",
      "Distance from previous stop",
      "Estimated arrival",
      "Waiting",
      "Service starts",
      "Investigation service",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText("Road travel")).toBeInTheDocument();
    expect(screen.getByText("Total service")).toBeInTheDocument();
  });

  it("shows cancelled investigations and their next workday on the agent view", () => {
    renderRoute({
      ...baseRoute,
      reason: "shift_unavailable",
      shift: { ...baseRoute.shift!, is_available: false },
      cancelled_investigations: [
        {
          id: 31,
          reference_number: "INV-0031",
          address_display: "31 Sample Road",
          status: "cancelled",
          reopen_on: "2026-11-03",
          priority: "normal",
          region_code: "1300000000",
          latitude: 14.74,
          longitude: 121.32,
        },
      ],
    });

    expect(screen.getByText("Paused until the next workday")).toBeInTheDocument();
    expect(screen.getByText("cancelled · reopens Nov 3, 2026")).toBeInTheDocument();
    expect(screen.getAllByText("INV-0031")).toHaveLength(2);
  });
});
