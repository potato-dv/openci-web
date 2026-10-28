import { expect, it } from "vitest";
import type { NewInvestigation } from "@/types/api";
import { investigationStepError } from "./investigationValidation";

const value = {
  first_name: "Fictional",
  last_name: "Subject",
  middle_name: null,
  service_duration_seconds: 2700,
  visit_not_before_at: null,
  visit_due_at: null,
  house_number: "12",
  street: "Example Road",
  region_code: "1300000000",
  city_municipality_code: "1374040000",
  barangay_code: "1374040010",
  postal_code: "",
} as NewInvestigation;

it("requires a complete address even while dependent select controls are disabled", () => {
  expect(
    investigationStepError(
      { ...value, city_municipality_code: "", barangay_code: "" },
      2,
    ),
  ).toContain("barangay");
  expect(investigationStepError(value, 2)).toBe("");
});

it("rejects blank names and invalid visit windows before saving a reviewed form", () => {
  expect(investigationStepError({ ...value, first_name: "   " }, 0)).not.toBe(
    "",
  );
  expect(
    investigationStepError(
      {
        ...value,
        visit_not_before_at: "2026-11-04T17:00:00+08:00",
        visit_due_at: "2026-11-04T08:00:00+08:00",
      },
      1,
    ),
  ).toContain("after");
  expect(
    investigationStepError({ ...value, service_duration_seconds: 0 }, 1),
  ).toContain("duration");
});
