import { describe, expect, it } from "vitest";
import type { PlanningMapData, PlanningRouteOverview } from "@/types/api";
import { buildPublishedRouteMapData } from "./publishedRouteData";

const inventory: PlanningMapData = {
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
      start: { latitude: 14.6, longitude: 121, label: "District Office" },
    },
    {
      id: 8,
      name: "Morgan Lee",
      is_active: true,
      region_code: null,
      is_available: null,
      shift_starts_at: null,
      shift_ends_at: null,
      start: null,
    },
  ],
  investigations: [
    {
      id: 11,
      reference_number: "INV-0011",
      address_display: "12 Example Street, Quezon City",
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
    {
      id: 12,
      reference_number: "INV-0012",
      address_display: "8 Sample Avenue, Makati",
      latitude: 14.55,
      longitude: 121.02,
      priority: "normal",
      status: "pending",
      region_code: "1300000000",
      assigned_agent_id: null,
      assigned_agent_name: null,
      service_duration_seconds: 2700,
      visit_not_before_at: null,
      visit_due_at: null,
    },
  ],
  unlocated_investigations: [
    { id: 13, reference_number: "INV-0013", status: "pending", region_code: "1300000000" },
  ],
  unlocated_agents: [{ id: 8, name: "Morgan Lee", is_active: true }],
};

const overview: PlanningRouteOverview = {
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
        start_location_label: "District Office",
        start_location_source: "manual",
        start_location_provider_ref: null,
        end_location_label: null,
        end_location_source: null,
        end_location_provider_ref: null,
        max_visits: 8,
        max_open_cases: 20,
        current_planning_run_id: 41,
      },
      route_status: "published",
      refresh_errors: [],
      refresh_investigation_id: 11,
      run_id: 41,
      planning_status: "idle",
      planning_error_code: null,
      planning_run_id: 41,
      open_case_count: 1,
      remaining_open_capacity: 19,
      route: {
        agent_id: 7,
        agent_name: "Avery Santos",
        geometry_status: "ready",
        geometry_error_code: null,
        geometry: { type: "LineString", coordinates: [[121, 14.6], [121.05, 14.65]] },
        geometry_digest: "digest",
        total_distance_metres: 4500,
        total_travel_seconds: 900,
        start: { latitude: 14.6, longitude: 121, label: "District Office" },
        end: null,
      },
      stops: [
        {
          service_duration_seconds: 1800,
          investigation_id: 11,
          reference_number: "INV-0011",
          address_display: "12 Example Street, Quezon City",
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
    {
      id: 8,
      name: "Morgan Lee",
      is_active: true,
      region_code: null,
      shift: null,
      route_status: "none",
      refresh_errors: [],
      refresh_investigation_id: null,
      run_id: null,
      planning_status: "idle",
      planning_error_code: null,
      planning_run_id: null,
      open_case_count: 0,
      remaining_open_capacity: null,
      route: null,
      stops: [],
    },
  ],
};

describe("buildPublishedRouteMapData", () => {
  it("merges every located investigation with the correct current route assignment", () => {
    const result = buildPublishedRouteMapData(
      inventory,
      overview,
      new Map([["1300000000", "Metro Manila"]]),
    );

    expect(result.agents).toHaveLength(1);
    expect(result.agents[0]).toMatchObject({
      id: 7,
      name: "Avery Santos",
      region_label: "Metro Manila",
      route_status: "published",
    });
    expect(result.investigations).toHaveLength(2);
    expect(result.investigations[0]).toMatchObject({
      id: 11,
      agent_id: 7,
      agent_name: "Avery Santos",
      sequence: 1,
    });
    expect(result.investigations[1]).toMatchObject({
      id: 12,
      agent_id: null,
      outcome: "unassigned",
    });
    expect(result.routes).toHaveLength(1);
    expect(result.routes[0].agent_id).toBe(7);
  });

  it("keeps assigned investigations visible without fabricating a route stop", () => {
    const result = buildPublishedRouteMapData(inventory, {
      ...overview,
      agents: overview.agents.map((agent) => ({ ...agent, route: null, stops: [], route_status: "failed" })),
    }, new Map());

    expect(result.investigations).toHaveLength(2);
    expect(result.investigations[0].agent_name).toBe("Avery Santos");
    expect(result.investigations[0].sequence).toBeNull();
    expect(result.routes).toHaveLength(0);
  });

  it("maps backend planning state and assignment source without inventing an assignment", () => {
    const result = buildPublishedRouteMapData(
      inventory,
      overview,
      new Map(),
      {
        work_date: "2026-10-23",
        region_code: null,
        total_investigations: 2,
        automatically_assigned: 1,
        unassigned_investigations: 1,
        active_agents: 2,
        available_agents: 1,
        optimizing_routes: 1,
        published_routes: 1,
        failed_planning_jobs: 0,
        investigation_states: [
          {
            investigation_id: 11,
            planning_status: "assigned",
            reason: null,
            planning_run_id: 41,
            assignment_source: "automatic",
          },
          {
            investigation_id: 12,
            planning_status: "optimizing",
            reason: null,
            planning_run_id: 42,
            assignment_source: null,
          },
        ],
      },
    );

    expect(result.investigations[0]).toMatchObject({
      planning_status: "assigned",
      assignment_source: "automatic",
    });
    expect(result.investigations[1]).toMatchObject({
      planning_status: "optimizing",
      agent_id: null,
      outcome: "unassigned",
      assignment_source: null,
    });
  });
});
