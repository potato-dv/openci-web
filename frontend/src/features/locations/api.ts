import type { GeocodeCandidate, LocationOption } from "@/types/api";
import { requestJson } from "@/services/http";

export function searchLocations(
  token: string,
  query: string,
  signal?: AbortSignal,
) {
  return requestJson<GeocodeCandidate[]>(
    `/locations/geocode-suggestions?q=${encodeURIComponent(query)}`,
    { token, signal },
  );
}

export function getRegions(token: string) {
  return requestJson<LocationOption[]>("/locations/regions", { token });
}

export function getProvinces(token: string, regionCode: string) {
  return requestJson<LocationOption[]>(
    `/locations/regions/${regionCode}/provinces`,
    { token },
  );
}

export function getCities(
  token: string,
  regionCode: string,
  provinceCode?: string,
) {
  const query = provinceCode ? `?province_code=${provinceCode}` : "";
  return requestJson<LocationOption[]>(
    `/locations/regions/${regionCode}/cities-municipalities${query}`,
    { token },
  );
}

export function getBarangays(token: string, cityCode: string) {
  return requestJson<LocationOption[]>(
    `/locations/cities-municipalities/${cityCode}/barangays`,
    { token },
  );
}
