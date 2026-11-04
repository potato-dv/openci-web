import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Investigation, Report } from "@/types/api";

vi.mock("@/features/reports/api", () => ({
  getReport: vi.fn(),
  getReportVersions: vi.fn(),
  getReviews: vi.fn(),
  reviewReport: vi.fn(),
}));

import { getReport, getReportVersions, getReviews } from "@/features/reports/api";
import { ReviewPanel } from "./ReviewPanel";

const report: Report = {
  id: 9,
  investigation_id: 42,
  author_id: 7,
  author_name: "Alex Agent",
  version: 1,
  content: "The residence was located and the property details were verified with the occupant.",
  visit_outcome: "visited",
  outcome: "verified",
  verified_address: "10 Sample Road, Region One",
  occupancy_status: "occupied",
  property_condition: "Well maintained",
  interaction_notes: "Confirmed residency and contact details.",
  visited_at: "2026-11-03T10:45:00+08:00",
  status: "submitted",
  created_at: "2026-11-03T11:00:00+08:00",
  updated_at: "2026-11-03T11:00:00+08:00",
  submitted_at: "2026-11-03T11:00:00+08:00",
};

describe("ReviewPanel", () => {
  beforeEach(() => {
    vi.mocked(getReport).mockResolvedValue(report);
    vi.mocked(getReportVersions).mockResolvedValue([report]);
    vi.mocked(getReviews).mockResolvedValue([]);
  });

  it("presents the agent's findings as the primary review result", async () => {
    const investigation = { id: 42 } as Investigation;
    const { container } = render(
      <ReviewPanel
        token="test-token"
        investigation={investigation}
        onChanged={vi.fn()}
      />,
    );

    expect(await screen.findByRole("heading", { name: "Agent findings" })).toBeInTheDocument();
    expect(screen.getByText("Detailed notes recorded during the field visit")).toBeInTheDocument();
    expect(screen.getByText(report.content)).toBeInTheDocument();
    expect(container.querySelector(".report-visit-result")).toHaveClass("is-visited");
    expect(screen.getByText("verified")).toHaveClass("report-fact-badge", "is-verified");
  });
});
