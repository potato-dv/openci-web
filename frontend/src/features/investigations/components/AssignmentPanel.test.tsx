import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  assignInvestigation: vi.fn(),
  getAgentRoster: vi.fn(),
  getAssignments: vi.fn(),
  retryInvestigationRoute: vi.fn(),
  submitAutomaticAssignment: vi.fn(),
  unassignInvestigation: vi.fn(),
}));

vi.mock("@/features/investigations/api", () => ({
  assignInvestigation: api.assignInvestigation,
  getAssignments: api.getAssignments,
  retryInvestigationRoute: api.retryInvestigationRoute,
  submitAutomaticAssignment: api.submitAutomaticAssignment,
  unassignInvestigation: api.unassignInvestigation,
}));
vi.mock("@/features/agents/api", () => ({
  getAgentRoster: api.getAgentRoster,
}));

import { AssignmentPanel } from "./AssignmentPanel";
import type { Assignment, AssignmentRouteRefresh, Investigation, User } from "@/types/api";

const investigation: Investigation = {
  id: 45,
  reference_number: "INV-TEST-45",
  first_name: "Case",
  middle_name: null,
  last_name: "Example",
  subject_name: "Case Example",
  legacy_address: null,
  address_display: "10 Test Road",
  house_number: "10",
  unit_floor_building_name: null,
  street: "Test Road",
  subdivision_village_purok: null,
  region_code: "1300000000",
  province_code: null,
  city_municipality_code: "1300000000",
  barangay_code: "1300000000",
  postal_code: null,
  status: "pending",
  priority: "normal",
    location_confirmed: true,
    assigned_agent_id: null,
};

const agent: User = {
  id: 7,
  name: "Alex Agent",
  email: "alex@example.test",
  role: "agent",
  is_active: true,
};

function assignment(routeStatus: AssignmentRouteRefresh["status"], errors: string[] = []): Assignment {
  return {
    id: 101,
    investigation_id: investigation.id,
    agent_id: agent.id,
    agent_name: agent.name,
    assigned_by_id: 1,
    assigned_by_name: "Supervisor",
    assignment_source: "manual",
    note: null,
    is_active: true,
    assigned_at: "2026-10-23T08:00:00+08:00",
    unassigned_at: null,
    route_refresh: {
      status: routeStatus,
      work_date: "2026-10-23",
      agent_ids: [agent.id],
      run_ids: [201],
      errors,
    },
  };
}

function renderPanel() {
  return render(
    <AssignmentPanel token="token" investigation={investigation} onChanged={vi.fn()} />,
  );
}

describe("AssignmentPanel automatic route refresh", () => {
  beforeEach(() => {
    api.assignInvestigation.mockReset();
    api.getAgentRoster.mockReset();
    api.getAssignments.mockReset();
    api.retryInvestigationRoute.mockReset();
    api.submitAutomaticAssignment.mockReset();
    api.unassignInvestigation.mockReset();
    api.getAgentRoster.mockResolvedValue([{
      agent,
      shift: {
        id: 71,
        agent_id: agent.id,
        work_date: "2026-10-23",
        region_code: investigation.region_code,
        is_available: true,
        shift_starts_at: "2026-10-23T08:00:00+08:00",
        shift_ends_at: "2026-10-23T17:00:00+08:00",
        start_latitude: 14.6,
        start_longitude: 121.1,
        end_latitude: null,
        end_longitude: null,
        max_visits: 10,
        max_open_cases: 30,
        current_planning_run_id: null,
      },
      assigned_workload_count: 0,
      visit_workload_count: 0,
    }]);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows queued then published when the assignment route refresh completes", async () => {
    const user = userEvent.setup();
    api.getAssignments
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([assignment("published")]);
    api.assignInvestigation.mockResolvedValue(assignment("queued"));

    renderPanel();
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    await user.selectOptions(screen.getByLabelText("Agent"), String(agent.id));
    await user.click(screen.getByRole("button", { name: "Apply manual override" }));

    expect(screen.getByText("Route update queued")).toBeInTheDocument();
    expect(await screen.findByText("Route published", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByText("Today’s validated road route is now available to the agent.")).toBeInTheDocument();
  });

  it("explains a missing shift and retries a failed route refresh", async () => {
    const failed = assignment("failed", ["agent_shift_unavailable_today"]);
    api.getAssignments.mockResolvedValue([failed]);
    api.retryInvestigationRoute.mockResolvedValue(assignment("queued"));

    renderPanel();
    expect(await screen.findByText("Route update failed")).toBeInTheDocument();
    expect(screen.getByText("This agent needs an available shift for today before a route can be built.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry route" }));

    expect(api.retryInvestigationRoute).toHaveBeenCalledWith("token", investigation.id);
    expect(screen.getByText("Route update queued")).toBeInTheDocument();
  });
});
