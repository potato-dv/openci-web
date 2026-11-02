import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Investigation, Report, RevisitRequest } from "@/types/api";

const api = vi.hoisted(() => ({
  getReport: vi.fn(),
  getReportVersions: vi.fn(),
  getRevisitRequest: vi.fn(),
  requestRevisit: vi.fn(),
  saveReport: vi.fn(),
  submitReport: vi.fn(),
}));

vi.mock("@/features/reports/api", () => api);

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
    api.getRevisitRequest.mockResolvedValue(null);
    api.requestRevisit.mockResolvedValue(pendingRequest);
  });

  it("requests the revisit explicitly and shows its waiting state", async () => {
    renderEditor();

    fireEvent.click(await screen.findByRole("button", { name: /request revisit route/i }));

    expect(api.requestRevisit).toHaveBeenCalledWith("token", investigation.id);
    expect(await screen.findByText(/Revisit requested for 2026-11-03/)).toBeInTheDocument();
  });

  it("keeps report submission disabled until a requested revisit route is published", async () => {
    api.getRevisitRequest.mockResolvedValue(pendingRequest);
    renderEditor();

    expect(await screen.findByText(/Submit after it is published/)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Submit report" })).toBeDisabled(),
    );
  });
});
