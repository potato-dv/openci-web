import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AgentWorkProfile, WeeklySchedule } from "@/types/api";

const mocks = vi.hoisted(() => ({
  getAgentAvailability: vi.fn(),
  getAgentWeeklySchedule: vi.fn(),
  getAgentWorkProfile: vi.fn(),
  saveAgentWeeklySchedule: vi.fn(),
  saveAgentWorkProfile: vi.fn(),
}));

vi.mock("@/features/agents/api", () => mocks);
vi.mock("@/components/map/LocationPicker", () => ({
  LocationPicker: ({
    onConfirm,
  }: {
    onConfirm: (point: {
      latitude: number;
      longitude: number;
      label: string;
      source: "manual";
      provider_ref: null;
    }) => void;
  }) => (
    <button
      type="button"
      onClick={() =>
        onConfirm({
          latitude: 14.6,
          longitude: 121.0,
          label: "Depot",
          source: "manual",
          provider_ref: null,
        })
      }
    >
      Confirm depot
    </button>
  ),
}));

import { AgentWeeklyScheduleEditor } from "./AgentWeeklyScheduleEditor";

const savedSchedule: WeeklySchedule = {
  region_code: "REGION-IVA",
  enabled: false,
  effective_from: "2026-11-01",
  max_visits: 6,
  max_open_cases: 15,
  days: Array.from({ length: 7 }, (_, weekday) => ({
    weekday,
    is_working: weekday === 0,
    shift_start: weekday === 0 ? "08:30" : null,
    shift_end: weekday === 0 ? "17:30" : null,
    break_start: weekday === 0 ? "12:00" : null,
    break_end: weekday === 0 ? "13:00" : null,
  })),
};

const workProfile: AgentWorkProfile = {
  depot_latitude: 14.6,
  depot_longitude: 121.0,
  depot_label: "Depot",
  depot_source: "manual",
  depot_provider_ref: null,
  end_latitude: null,
  end_longitude: null,
  end_label: null,
  end_source: null,
  end_provider_ref: null,
};

describe("AgentWeeklyScheduleEditor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getAgentAvailability.mockResolvedValue({ days: [] });
    mocks.getAgentWeeklySchedule.mockResolvedValue(savedSchedule);
    mocks.getAgentWorkProfile.mockResolvedValue(workProfile);
    mocks.saveAgentWeeklySchedule.mockResolvedValue(savedSchedule);
    mocks.saveAgentWorkProfile.mockResolvedValue(workProfile);
  });

  it("uses loaded schedule values and saves edits without effect-based form copies", async () => {
    render(
      <AgentWeeklyScheduleEditor
        token="session-token"
        agentId={7}
        date="2026-11-07"
        regions={[{ code: "REGION-IVA", name: "CALABARZON" }]}
        onDirty={vi.fn()}
        onUpdated={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByLabelText("Service region")).toHaveValue("REGION-IVA");
    });
    expect(screen.getByLabelText("Weekly schedule enabled")).not.toBeChecked();
    expect(screen.getByLabelText("Effective from")).toHaveValue("2026-11-01");
    expect(screen.getByLabelText("Maximum visits per day")).toHaveValue(6);

    fireEvent.change(screen.getByLabelText("Maximum visits per day"), {
      target: { value: "7" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save weekly schedule" }),
    );

    await waitFor(() => {
      expect(mocks.saveAgentWeeklySchedule).toHaveBeenCalledWith(
        "session-token",
        7,
        expect.objectContaining({
          region_code: "REGION-IVA",
          enabled: false,
          effective_from: "2026-11-01",
          max_visits: 7,
          max_open_cases: 15,
        }),
      );
    });
  });
});
