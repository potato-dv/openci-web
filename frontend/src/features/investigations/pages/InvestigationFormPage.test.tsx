import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Investigation, InvestigationLocation, User } from "@/types/api";

const api = vi.hoisted(() => ({
  confirmInvestigationLocation: vi.fn(),
  createInvestigation: vi.fn(),
  getInvestigation: vi.fn(),
  getInvestigationLocation: vi.fn(),
  updateInvestigation: vi.fn(),
  getBarangays: vi.fn(),
  getCities: vi.fn(),
  getProvinces: vi.fn(),
  getRegions: vi.fn(),
}));

vi.mock("@/features/investigations/api", () => ({
  confirmInvestigationLocation: api.confirmInvestigationLocation,
  createInvestigation: api.createInvestigation,
  getInvestigation: api.getInvestigation,
  getInvestigationLocation: api.getInvestigationLocation,
  updateInvestigation: api.updateInvestigation,
}));
vi.mock("@/features/locations/api", () => ({
  getBarangays: api.getBarangays,
  getCities: api.getCities,
  getProvinces: api.getProvinces,
  getRegions: api.getRegions,
}));
vi.mock("@/components/map/LocationPicker", () => ({
  LocationPicker: () => <div data-testid="location-picker" />,
}));

import { SessionContext } from "@/app/session";
import { InvestigationFormPage } from "./InvestigationFormPage";

const regionOne = "0100000000";
const regionTwo = "0200000000";
const provinceOne = "0102800000";
const cityOne = "0102801000";
const barangayOne = "0102801001";

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
  region_code: regionOne,
  province_code: provinceOne,
  city_municipality_code: cityOne,
  barangay_code: barangayOne,
  postal_code: "1000",
  status: "pending",
  priority: "high",
  location_confirmed: true,
  service_duration_seconds: 2700,
  visit_not_before_at: "2026-11-02T09:00:00+08:00",
  visit_due_at: "2026-11-02T15:00:00+08:00",
};

const location: InvestigationLocation = {
  latitude: 14.6,
  longitude: 121.0,
  source: "manual",
  provider_ref: null,
  confirmed_at: "2026-11-01T12:00:00+08:00",
  h3_r7: "r7",
  h3_r8: "r8",
  h3_r9: "r9",
};

const user: User = {
  id: 1,
  name: "Supervisor",
  email: "supervisor@example.test",
  role: "supervisor",
  is_active: true,
};

function renderEditPage() {
  return render(
    <MemoryRouter initialEntries={["/investigations/42/edit"]}>
      <SessionContext.Provider
        value={{ token: "test-token", user, logout() {} }}
      >
        <Routes>
          <Route
            path="/investigations/:id/edit"
            element={<InvestigationFormPage />}
          />
          <Route
            path="/investigations/:id"
            element={<p>Investigation record</p>}
          />
        </Routes>
      </SessionContext.Provider>
    </MemoryRouter>,
  );
}

describe("InvestigationFormPage edit layout", () => {
  beforeEach(() => {
    api.confirmInvestigationLocation.mockReset();
    api.createInvestigation.mockReset();
    api.getInvestigation.mockReset().mockResolvedValue(investigation);
    api.getInvestigationLocation.mockReset().mockResolvedValue(location);
    api.updateInvestigation.mockReset().mockResolvedValue(investigation);
    api.getRegions.mockReset().mockResolvedValue([
      { code: regionOne, name: "Region One" },
      { code: regionTwo, name: "Region Two" },
    ]);
    api.getProvinces.mockReset().mockImplementation(async (_token, code) => [
      {
        code: code === regionOne ? provinceOne : "0202800000",
        name: "Province",
      },
    ]);
    api.getCities
      .mockReset()
      .mockImplementation(async (_token, code) => [
        { code: code === regionOne ? cityOne : "0202801000", name: "City" },
      ]);
    api.getBarangays
      .mockReset()
      .mockResolvedValue([{ code: barangayOne, name: "Barangay" }]);
  });

  it("loads the selected investigation into the grouped edit form", async () => {
    renderEditPage();

    expect(
      await screen.findByRole("heading", { name: "Edit investigation" }),
    ).toBeInTheDocument();
    await screen.findByRole("option", { name: "Barangay" });
    expect(
      screen.getByRole("group", { name: "Personal information" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("group", { name: "Visit requirements" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("group", { name: "Investigation address" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("First name")).toHaveValue("Mara");
    expect(screen.getByLabelText("Middle name (optional)")).toHaveValue("Lee");
    expect(screen.getByLabelText("Last name")).toHaveValue("Santos");
    expect(screen.getByLabelText("Priority")).toHaveValue("high");
    expect(
      screen.getByLabelText("Estimated visit duration (minutes)"),
    ).toHaveValue(45);
    expect(screen.getByLabelText("Earliest visit (optional)")).toHaveValue(
      "2026-11-02T09:00",
    );
    expect(screen.getByLabelText("Completion deadline (optional)")).toHaveValue(
      "2026-11-02T15:00",
    );
    expect(screen.getByLabelText("House/building number")).toHaveValue("10");
    expect(screen.getByLabelText(/^Unit\/floor\/building name/)).toHaveValue(
      "Unit 2",
    );
    expect(screen.getByLabelText("Street")).toHaveValue("Sample Road");
    expect(screen.getByLabelText(/^Subdivision\/village\/purok/)).toHaveValue(
      "North Village",
    );
    expect(screen.getByLabelText("Region")).toHaveValue(regionOne);
    expect(screen.getByLabelText(/^Province/)).toHaveValue(provinceOne);
    expect(screen.getByLabelText("City/municipality")).toHaveValue(cityOne);
    expect(screen.getByLabelText("Barangay")).toHaveValue(barangayOne);
    expect(screen.getByLabelText(/^Postal code/)).toHaveValue("1000");
    expect(screen.getByTestId("location-picker")).toBeInTheDocument();
    expect(api.getInvestigation).toHaveBeenCalledWith(
      "test-token",
      42,
      expect.any(AbortSignal),
    );
  });

  it("validates required subject information and saves edits through the existing update API", async () => {
    const user = userEvent.setup();
    renderEditPage();

    await screen.findByRole("option", { name: "Barangay" });
    const firstName = await screen.findByLabelText("First name");
    await user.clear(firstName);
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect((firstName as HTMLInputElement).validity.valueMissing).toBe(true);
    expect(api.updateInvestigation).not.toHaveBeenCalled();

    await user.type(firstName, "Maria");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText("Investigation record");

    expect(api.updateInvestigation).toHaveBeenCalledWith("test-token", 42, {
      first_name: "Maria",
      middle_name: "Lee",
      last_name: "Santos",
    });
    expect(api.confirmInvestigationLocation).not.toHaveBeenCalled();
  });

  it("clears dependent address selections when the region changes", async () => {
    const user = userEvent.setup();
    renderEditPage();
    await screen.findByRole("group", { name: "Personal information" });
    await screen.findByRole("option", { name: "Region Two" });

    await user.selectOptions(screen.getByLabelText("Region"), regionTwo);

    await waitFor(() => {
      expect(api.getCities).toHaveBeenCalledWith(
        "test-token",
        regionTwo,
        undefined,
      );
    });
    expect(screen.getByLabelText(/^Province/)).toHaveValue("");
    expect(screen.getByLabelText("City/municipality")).toHaveValue("");
    expect(screen.getByLabelText("Barangay")).toHaveValue("");
  });

  it("cancels back to the selected investigation", async () => {
    const user = userEvent.setup();
    renderEditPage();

    await user.click(await screen.findByRole("link", { name: "Cancel" }));

    expect(await screen.findByText("Investigation record")).toBeInTheDocument();
  });
});
