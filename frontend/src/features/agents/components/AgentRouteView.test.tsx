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
  route_revision: null,
  current_actionable_investigation_id: null,
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
  attempt_history: [],
  deferred_attempts: [],
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

  it("shows VROOM departure, arrival, stop wait, service times, and travel separately", () => {
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
        total_distance_metres: 15196,
        total_travel_seconds: 1069,
        total_service_seconds: 1200,
        total_waiting_seconds: 0,
        total_planned_waiting_seconds: 0,
        total_break_seconds: 0,
        planned_departure_at: "2026-11-04T02:42:11Z",
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
          estimated_arrival_at: "2026-11-04T01:22:22Z",
          earliest_arrival_estimate_at: "2026-11-04T01:22:22Z",
          planned_arrival_at: "2026-11-04T03:00:00Z",
          estimated_service_start_at: "2026-11-04T03:00:00Z",
          waiting_seconds: 0,
          planned_waiting_seconds: 0,
          travel_seconds: 1069,
          travel_metres: 15196,
          latitude: 14.73,
          longitude: 121.31,
          priority: "normal",
          status: "assigned",
          sequence_state: "current",
          actionable: true,
          can_start: true,
          can_report: false,
          active_attempt_id: null,
          can_finalize_no_contact: false,
          priority_order_exception_reason: null,
          attempt_history: [],
        },
      ],
    });

    for (const label of [
      "Travel from previous stop",
      "Distance from previous stop",
      "Earliest arrival estimate · depart as soon as possible",
      "Planned departure",
      "Planned arrival",
      "Wait at stop",
      "Service starts",
      "Service ends",
      "Investigation service",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText("normal")).toHaveClass("priority-normal");
    expect(screen.getByText("9:22 AM")).toBeInTheDocument();
    expect(screen.getByText("10:42 AM")).toBeInTheDocument();
    expect(screen.getAllByText("11:00 AM")).toHaveLength(2);
    expect(screen.getByText("11:20 AM")).toBeInTheDocument();
    expect(screen.getAllByText("No scheduled wait")).toHaveLength(2);
    expect(screen.getAllByText("18 min")).toHaveLength(2);
    expect(screen.queryByText("1h 38m")).not.toBeInTheDocument();
    expect(screen.getByText("Road travel")).toBeInTheDocument();
    expect(screen.getByText("Total service")).toBeInTheDocument();
  });

  it("does not present legacy timestamp gaps as VROOM waiting", () => {
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
        total_distance_metres: 15196,
        total_travel_seconds: 1069,
        total_service_seconds: 1200,
        total_waiting_seconds: null,
        total_planned_waiting_seconds: null,
        total_break_seconds: 0,
        start: { latitude: 14.72, longitude: 121.3, label: "Latest completed visit (estimated)" },
        end: null,
      },
      stops: [{
        service_duration_seconds: 1200,
        investigation_id: 21,
        reference_number: "INV-0021",
        address_display: "21 Sample Road",
        sequence: 1,
        estimated_arrival_at: "2026-11-04T01:22:22Z",
        estimated_service_start_at: "2026-11-04T03:00:00Z",
        waiting_seconds: 5858,
        travel_seconds: 1069,
        travel_metres: 15196,
        latitude: 14.73,
        longitude: 121.31,
        priority: "normal",
        status: "assigned",
        sequence_state: "current",
        actionable: true,
        can_start: true,
        can_report: false,
        active_attempt_id: null,
        can_finalize_no_contact: false,
        priority_order_exception_reason: null,
        attempt_history: [],
      }],
    });

    expect(screen.getAllByText("Not available")).toHaveLength(4);
    expect(screen.queryByText("1h 38m")).not.toBeInTheDocument();
    expect(screen.getByText("11:00 AM")).toBeInTheDocument();
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

    expect(screen.getAllByText("Paused until the next workday")).toHaveLength(2);
    expect(screen.getByText("cancelled · reopens Nov 3, 2026")).toBeInTheDocument();
    expect(screen.getAllByText("INV-0031")).toHaveLength(2);
  });

  it("labels the current stop and keeps upcoming stops view-only", () => {
    renderRoute({
      ...baseRoute,
      reason: null,
      route_revision: 12,
      current_actionable_investigation_id: 21,
      stops: [
        {
          service_duration_seconds: 1800,
          investigation_id: 21,
          reference_number: "INV-0021",
          address_display: "21 Sample Road",
          sequence: 1,
          estimated_arrival_at: null,
          planned_arrival_at: "2026-11-05T01:00:00Z",
          estimated_service_start_at: "2026-11-05T01:00:00Z",
          waiting_seconds: 0,
          planned_waiting_seconds: 0,
          travel_seconds: 600,
          travel_metres: 5000,
          latitude: 14.73,
          longitude: 121.31,
          priority: "urgent",
          status: "assigned",
          sequence_state: "current",
          actionable: true,
          can_start: true,
          can_report: false,
          active_attempt_id: null,
          can_finalize_no_contact: false,
          priority_order_exception_reason: null,
          attempt_history: [],
        },
        {
          service_duration_seconds: 1800,
          investigation_id: 22,
          reference_number: "INV-0022",
          address_display: "22 Sample Road",
          sequence: 2,
          estimated_arrival_at: null,
          planned_arrival_at: "2026-11-05T02:00:00Z",
          estimated_service_start_at: "2026-11-05T02:00:00Z",
          waiting_seconds: 0,
          planned_waiting_seconds: 0,
          travel_seconds: 900,
          travel_metres: 7000,
          latitude: 14.74,
          longitude: 121.32,
          priority: "normal",
          status: "assigned",
          sequence_state: "upcoming",
          actionable: false,
          can_start: false,
          can_report: false,
          active_attempt_id: null,
          can_finalize_no_contact: false,
          priority_order_exception_reason: null,
          attempt_history: [],
        },
      ],
    });

    expect(screen.getByText("Current stop")).toBeInTheDocument();
    expect(screen.getByText("Upcoming")).toBeInTheDocument();
    expect(
      screen.getAllByRole("status").some((item) =>
        item.textContent?.includes("Upcoming stops stay view-only until this stop is submitted or deferred."),
      ),
    ).toBe(true);
    expect(screen.getByText("urgent")).toHaveClass("priority-urgent");
  });

  it("shows deferred retry and shift-end carry-over separately", () => {
    render(
      <MemoryRouter>
        <AgentRouteView
          data={{
            ...baseRoute,
            route_revision: 12,
            deferred_attempts: [
              {
                id: 41,
                investigation_id: 41,
                reference_number: "INV-NO-CONTACT",
                address_display: "41 Sample Road",
                priority: "high",
                agent_id: 7,
                work_date: "2026-11-02",
                planning_run_id: 12,
                parent_event_id: 40,
                event_type: "no_contact",
                state: "retry_failed",
                retry_number: 1,
                reason: "nobody_at_location",
                notes: null,
                contact_available_from: null,
                contact_available_until: null,
                attempted_at: "2026-11-02T04:00:00Z",
                next_work_date: "2026-11-06",
                finalized_at: null,
                can_finalize_no_contact: true,
                retry_actionable: false,
              },
              {
                id: 42,
                investigation_id: 42,
                reference_number: "INV-NOT-VISITED",
                address_display: "42 Sample Road",
                priority: "normal",
                agent_id: 7,
                work_date: "2026-11-02",
                planning_run_id: 12,
                parent_event_id: null,
                event_type: "shift_end_not_visited",
                state: "carried_over",
                retry_number: 0,
                reason: "shift_end_not_visited",
                notes: null,
                contact_available_from: null,
                contact_available_until: null,
                attempted_at: "2026-11-02T09:00:00Z",
                next_work_date: "2026-11-06",
                finalized_at: "2026-11-02T09:00:00Z",
                can_finalize_no_contact: false,
                retry_actionable: false,
              },
            ],
          }}
          agentId={7}
          agentName="Avery Santos"
          token="token"
          canAct
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole("region", { name: "Deferred and carried-over investigations" })).toBeInTheDocument();
    expect(screen.getByText("Retry used · carry-over ready")).toBeInTheDocument();
    expect(screen.getByText("Shift End — Not Visited")).toBeInTheDocument();
    expect(screen.getByText("Next work date: 2026-11-06")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit No Contact Report" })).toBeInTheDocument();
  });
});
