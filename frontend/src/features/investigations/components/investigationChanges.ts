import type { InvestigationUpdate, NewInvestigation } from "@/types/api";
export function investigationChanges(
  original: NewInvestigation,
  current: NewInvestigation,
): InvestigationUpdate {
  const changes = Object.fromEntries(
    Object.entries(current).filter(
      ([key, value]) => value !== original[key as keyof NewInvestigation],
    ),
  ) as InvestigationUpdate;
  if (
    ["first_name", "middle_name", "last_name"].some((key) => key in changes)
  ) {
    Object.assign(changes, {
      first_name: current.first_name,
      middle_name: current.middle_name,
      last_name: current.last_name,
    });
  }
  if (
    [
      "region_code",
      "province_code",
      "city_municipality_code",
      "barangay_code",
    ].some((key) => key in changes)
  ) {
    Object.assign(changes, {
      house_number: current.house_number,
      street: current.street,
      region_code: current.region_code,
      province_code: current.province_code || null,
      city_municipality_code: current.city_municipality_code,
      barangay_code: current.barangay_code,
    });
  }
  return changes;
}
