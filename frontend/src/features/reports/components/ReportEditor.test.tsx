import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AgentRoute, Investigation, Report, RevisitRequest } from "@/types/api";

const api = vi.hoisted(() => ({
  getReport: vi.fn(),
  getReportVersions: vi.fn(),
  getRevisitRequest: vi.fn(),
  requestRevisit: vi.fn(),
  saveReport: vi.fn(),
  submitReport: vi.fn(),
}));
const routeApi = vi.hoisted(() => ({ getAgentRoute: vi.fn() }));

vi.mock("@/features/reports/api", () => api);
vi.mock("@/features/route-planning/api", () => routeApi);

import { ReportEditor } from "./ReportEditor";

const investigation = {
  id: 44,
  reference_number: "INV-0044",
  first_name: "Taylor",
  middle_name: null,
  last_name: "Example",
  subject_name: "Taylor Example",
  legacy_address: null,
  address_display: "44 Sample Street",
  house_number: "44",
  unit_floor_building_name: null,
  street: "Sample Street",
  subdivision_village_purok: null,
  region_code: "1300000000",
  province_code: null,
  city_municipality_code: null,
  barangay_code: null,
  postal_code: null,
  status: "returned_for_correction",
  priority: "normal",
} as Investigation;

const returnedReport: Report = {
  id: 51,
  investigation_id: 44,
  author_id: 7,
  author_name: "Agent Example",
  version: 1,
  content: "Original visit findings",
  visit_outcome: "visited",
  outcome: "verified",
  verified_address: "44 Sample Street",
  occupancy_status: null,
  property_condition: null,
  interaction_notes: null,
  visited_at: "2026-11-02T03:00:00Z",
  status: "returned_for_correction",
  created_at: "2026-11-02T03:00:00Z",
  updated_at: "2026-11-02T03:00:00Z",
  submitted_at: "2026-11-02T03:00:00Z",
};

const pendingRequest: RevisitRequest = {
  id: 60,
  investigation_id: 44,
  reference_number: "INV-0044",
  report_id: 51,
  agent_id: 7,
  target_work_date: "2026-11-03",
  status: "waiting_for_shift",
  planning_run_id: null,
  created_at: "2026-11-02T03:10:00Z",
  completed_at: null,
};

function routeForStop(
  overrides: Partial<AgentRoute["stops"][number]> = {},
  currentId = investigation.id,
): AgentRoute {
  const stop = {
    service_duration_seconds: 1800,
    investigation_id: investigation.id,
    reference_number: investigation.reference_number,
    address_display: investigation.address_display,
    sequence: 1,
    estimated_arrival_at: null,
    earliest_arrival_estimate_at: null,
    planned_arrival_at: null,
    estimated_service_start_at: null,
    waiting_seconds: null,
    planned_waiting_seconds: null,
    travel_seconds: null,
    travel_metres: null,
    latitude: 14.65,
    longitude: 121.05,
    priority: "high" as const,
    status: "returned_for_correction" as const,
    sequence_state: "current" as const,
    actionable: true,
    can_start: false,
    can_report: true,
    active_attempt_id: null,
    can_finalize_no_contact: false,
    priority_order_exception_reason: null,
    attempt_history: [],
    ...overrides,
  };
  return {
    work_date: "2026-11-05",
    route_revision: 3,
    current_actionable_investigation_id: currentId,
    reason: null,
    shift: null,
    route: null,
    stops: [stop],
  };
}

function renderEditor() {
  return render(
    <MemoryRouter>
      <ReportEditor token="token" investigation={investigation} onChanged={vi.fn()} />
    </MemoryRouter>,
  );
}

describe("ReportEditor revisit action", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getReport.mockResolvedValue(returnedReport);
    api.getReportVersions.mockResolvedValue([returnedReport]);
    api.getRevisitRequest.mockResolvedValue({ request: null, can_request: true });
    api.requestRevisit.mockResolvedValue(pendingRequest);
    routeApi.getAgentRoute.mockResolvedValue(null);
  });

  it("requests the revisit explicitly and shows its waiting state", async () => {
    renderEditor();

    fireEvent.click(await screen.findByRole("button", { name: /request revisit route/i }));

    expect(api.requestRevisit).toHaveBeenCalledWith("token", investigation.id);
    expect(await screen.findByText(/Revisit requested for 2026-11-03/)).toBeInTheDocument();
  });

  it("keeps report submission disabled until a requested revisit route is published", async () => {
    api.getRevisitRequest.mockResolvedValue({ request: pendingRequest, can_request: false });
    renderEditor();

    expect(await screen.findByText(/Submit after it is published/)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Submit report" })).not.toBeInTheDocument(),
    );
  });

  it("does not fetch earlier report versions when history is denied but still uses revisit eligibility", async () => {
    render(
      <MemoryRouter>
        <ReportEditor
          token="token"
          investigation={investigation}
          onChanged={vi.fn()}
          canViewEarlierReportVersions={false}
        />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("button", { name: /request revisit route/i })).toBeInTheDocument();
    expect(api.getReportVersions).not.toHaveBeenCalled();
  });

  it("enables report actions only for the current actionable stop", async () => {
    routeApi.getAgentRoute.mockResolvedValue(routeForStop());
    renderEditor();

    expect(await screen.findByRole("button", { name: "Submit report" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Save draft" })).toBeEnabled();
  });

  it("offers retry only after the deferred stop becomes actionable", async () => {
    routeApi.getAgentRoute.mockResolvedValue(routeForStop({
      sequence_state: "deferred_retry",
      actionable: true,
      can_start: true,
      can_report: false,
    }));
    renderEditor();

    expect(await screen.findByRole("button", { name: "Retry Investigation" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Submit report" })).not.toBeInTheDocument();
  });

  it("keeps an upcoming investigation view-only", async () => {
    routeApi.getAgentRoute.mockResolvedValue(routeForStop({
      sequence_state: "upcoming",
      actionable: false,
      can_start: false,
      can_report: false,
    }, 99));
    renderEditor();

    expect(await screen.findByText(/upcoming investigation/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start Current Investigation" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Submit report" })).not.toBeInTheDocument();
  });
});
