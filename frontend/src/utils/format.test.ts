import { describe, expect, it } from "vitest";
import { friendlyError, plannedWait, time, timeAfter } from "./format";

describe("planning error copy", () => {
  it.each([
    "planning_dependencies_unavailable",
    "dataset_unconfigured",
    "worker_unavailable",
    "osrm_unavailable",
    "vroom_unavailable",
    "queue_unavailable",
    "osrm_snap_failed",
    "osrm_snap_shape_invalid",
    "osrm_table_unavailable",
    "osrm_table_failed",
    "osrm_matrix_shape_invalid",
    "vroom_solver_failed",
    "osrm_route_unavailable",
    "osrm_route_failed",
    "osrm_route_shape_invalid",
    "route_geometry_invalid",
    "optimization_failed",
    "inputs_changed",
    "shift_changed",
    "investigation_changed",
    "no_eligible_agents",
    "no_eligible_investigations",
    "no_feasible_visit_windows",
    "agent_start_off_road",
    "assignment_lock_conflict",
    "locked_case_not_feasible",
    "route_geometry_incomplete",
    "stale_plan",
  ])("translates %s into actionable copy", (code) => {
    expect(friendlyError(code)).not.toBe(code.replaceAll("_", " "));
  });
});

describe("route schedule formatting", () => {
  it("formats planned schedule timestamps in Manila time", () => {
    expect(time("2026-11-04T03:00:00Z")).toBe("11:00 AM");
    expect(timeAfter("2026-11-04T03:00:00Z", 2700)).toBe("11:45 AM");
  });

  it("distinguishes known, zero, and unavailable stop waiting", () => {
    expect(plannedWait(0)).toBe("No scheduled wait");
    expect(plannedWait(300)).toBe("5 min");
    expect(plannedWait(null)).toBe("Not available");
  });
});
