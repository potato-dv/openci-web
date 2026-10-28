import { expect, it } from "vitest";
import { investigationChanges } from "./investigationChanges";
import type { NewInvestigation } from "@/types/api";
const initial: NewInvestigation = {
  first_name: "Fictional",
  middle_name: null,
  last_name: "Subject",
  house_number: "10",
  unit_floor_building_name: "",
  street: "Example Street",
  subdivision_village_purok: "",
  region_code: "1300000000",
  province_code: "",
  city_municipality_code: "1374040000",
  barangay_code: "1374040010",
  postal_code: "",
  priority: "normal",
  service_duration_seconds: 2700,
  visit_not_before_at: null,
  visit_due_at: null,
};
it("does not invalidate location or plans when nothing changed", () => {
  expect(investigationChanges(initial, { ...initial })).toEqual({});
});
it("sends only the changed planning detail", () => {
  expect(
    investigationChanges(initial, { ...initial, priority: "urgent" }),
  ).toEqual({ priority: "urgent" });
});
it("sends complete name parts when a subject name is edited", () => {
  expect(
    investigationChanges(initial, { ...initial, last_name: "Updated" }),
  ).toEqual({
    first_name: "Fictional",
    middle_name: null,
    last_name: "Updated",
  });
});
it("sends complete geography and required street fields together", () => {
  expect(
    investigationChanges(initial, { ...initial, barangay_code: "1374040011" }),
  ).toMatchObject({
    house_number: "10",
    street: "Example Street",
    region_code: "1300000000",
    province_code: null,
    city_municipality_code: "1374040000",
    barangay_code: "1374040011",
  });
});
