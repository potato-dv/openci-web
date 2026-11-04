import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import type { Investigation, User } from "@/types/api";

vi.mock("@/features/investigations/api", () => ({
  deleteInvestigation: vi.fn(),
}));
vi.mock("@/features/investigations/components/AssignmentPanel", () => ({
  AssignmentPanel: () => null,
}));
vi.mock("@/features/investigations/components/LocationConfirmationPanel", () => ({
  LocationConfirmationPanel: () => null,
}));
vi.mock("@/features/reports/components/ReportEditor", () => ({
  ReportEditor: () => null,
}));
vi.mock("@/features/reports/components/ReviewPanel", () => ({
  ReviewPanel: () => null,
}));

import { InvestigationDetailsPage } from "./InvestigationDetailsPage";

const investigation: Investigation = {
  id: 42,
  reference_number: "INV-2026-0042",
  first_name: "Mara",
  middle_name: "Lee",
  last_name: "Santos",
  subject_name: "Mara Lee Santos",
  legacy_address: null,
  address_display: "10 Sample Road, Region One",
  house_number: "10",
  unit_floor_building_name: "Unit 2",
  street: "Sample Road",
  subdivision_village_purok: "North Village",
  region_code: "0100000000",
  province_code: "0102800000",
  city_municipality_code: "0102801000",
  barangay_code: "0102801001",
  postal_code: "1000",
  status: "pending",
  priority: "high",
  assigned_agent_id: 7,
  assigned_agent_name: "Alex Agent",
  location_confirmed: true,
  service_duration_seconds: 5400,
  visit_not_before_at: "2026-11-02T09:00:00+08:00",
  visit_due_at: "2026-11-02T15:00:00+08:00",
};

const agent: User = {
  id: 7,
  name: "Alex Agent",
  email: "alex@example.test",
  role: "agent",
  is_active: true,
};

function renderDetails(item = investigation, currentUser = agent) {
  return render(
    <MemoryRouter>
      <InvestigationDetailsPage
        token="test-token"
        user={currentUser}
        investigation={item}
        onChanged={vi.fn()}
        onDeleted={vi.fn()}
      />
    </MemoryRouter>,
  );
}

describe("InvestigationDetailsPage", () => {
  it("places manager workflows in a two-column workspace", () => {
    const manager: User = { ...agent, id: 3, role: "supervisor" };
    const { container } = renderDetails(investigation, manager);
    const workspace = container.querySelector(".investigation-workspace-grid");

    expect(container.querySelector(".investigation-manager-details")).toBeInTheDocument();
    expect(workspace?.children).toHaveLength(2);
    expect(workspace?.firstElementChild).toHaveClass("investigation-planning-column");
    expect(workspace?.querySelector("#assignment")).toBeInTheDocument();
    expect(workspace?.querySelector("#report")).toBeInTheDocument();
  });

  it("organizes the overview and existing visit requirements", () => {
    renderDetails();

    expect(
      screen.getByRole("heading", { name: "Mara Lee Santos" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Reference")).toBeInTheDocument();
    expect(screen.getByText("INV-2026-0042")).toBeInTheDocument();
    expect(screen.getByText("Investigation status")).toBeInTheDocument();
    expect(screen.getByText("10 Sample Road, Region One")).toBeInTheDocument();
    expect(screen.getByText("Alex Agent")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Visit requirements" })).toBeInTheDocument();
    expect(screen.getByText("1h 30m")).toBeInTheDocument();
    expect(screen.getByText("All times use Philippine time (UTC+8).")).toBeInTheDocument();
    const visitTimes = screen.getAllByText(/Nov 2, 2026/);
    expect(visitTimes).toHaveLength(2);
    expect(visitTimes[0]).toHaveTextContent("9:00 AM");
    expect(visitTimes[1]).toHaveTextContent("3:00 PM");
  });

  it("explains when no visit window has been set", () => {
    renderDetails({
      ...investigation,
      visit_not_before_at: null,
      visit_due_at: null,
    });

    expect(screen.getByText("No earliest visit set")).toBeInTheDocument();
    expect(screen.getByText("No deadline set")).toBeInTheDocument();
  });
});
