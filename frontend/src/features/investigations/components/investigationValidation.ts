import type { NewInvestigation } from "@/types/api";

export function investigationStepError(
  value: NewInvestigation,
  step: number,
): string {
  if (step === 0) {
    if (!value.first_name.trim() || !value.last_name.trim())
      return "Enter the subject’s first and last name.";
    const name = [value.first_name, value.middle_name, value.last_name]
      .filter(Boolean)
      .join(" ")
      .trim()
      .replace(/\s+/g, " ");
    if (name.length > 255)
      return "The combined subject name must contain no more than 255 characters.";
  }
  if (step === 1) {
    if (
      !Number.isInteger(value.service_duration_seconds) ||
      value.service_duration_seconds < 300 ||
      value.service_duration_seconds > 28800
    )
      return "Set a visit duration between 5 and 480 minutes.";
    const start = value.visit_not_before_at
      ? Date.parse(value.visit_not_before_at)
      : null;
    const end = value.visit_due_at ? Date.parse(value.visit_due_at) : null;
    if (
      (start !== null && !Number.isFinite(start)) ||
      (end !== null && !Number.isFinite(end))
    )
      return "Enter a valid visit date and time.";
    if (start !== null && end !== null && end <= start)
      return "The completion deadline must be after the earliest visit time.";
  }
  if (step === 2) {
    if (!value.house_number.trim() || !value.street.trim())
      return "Enter the house or building number and street.";
    if (
      ![
        value.region_code,
        value.city_municipality_code,
        value.barangay_code,
      ].every((code) => /^\d{10}$/.test(code))
    )
      return "Select the region, city or municipality, and barangay before continuing.";
    if (value.postal_code && !/^\d{4}$/.test(value.postal_code))
      return "Enter a four digit postal code or leave it blank.";
  }
  return "";
}
