import { describe, expect, it } from "vitest";
import { friendlyError } from "./format";

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
