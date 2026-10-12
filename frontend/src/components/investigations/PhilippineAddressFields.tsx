import { useEffect, useState } from "react";

import { getBarangays, getCities, getProvinces, getRegions } from "../../services/api";
import type { LocationOption, NewInvestigation } from "../../types/api";

type Props = {
  token: string;
  value: NewInvestigation;
  onChange: (next: NewInvestigation) => void;
};

export function PhilippineAddressFields({ token, value, onChange }: Props) {
  const [regions, setRegions] = useState<LocationOption[]>([]);
  const [provinces, setProvinces] = useState<LocationOption[]>([]);
  const [cities, setCities] = useState<LocationOption[]>([]);
  const [barangays, setBarangays] = useState<LocationOption[]>([]);
  const [loading, setLoading] = useState({ regions: false, provinces: false, cities: false, barangays: false });
  const [error, setError] = useState("");
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getRegions(token).then((items) => { if (!cancelled) setRegions(items); })
      .catch((err: unknown) => { if (!cancelled) setError(err instanceof Error ? err.message : "Could not load regions."); })
      .finally(() => { if (!cancelled) setLoading((current) => ({ ...current, regions: false })); });
    return () => { cancelled = true; };
  }, [retryKey, token]);

  useEffect(() => {
    if (!value.region_code) {
      return;
    }
    let cancelled = false;
    Promise.all([getProvinces(token, value.region_code), getCities(token, value.region_code, value.province_code || undefined)])
      .then(([provinceItems, cityItems]) => {
        if (!cancelled) { setProvinces(provinceItems); setCities(cityItems); }
      })
      .catch((err: unknown) => { if (!cancelled) setError(err instanceof Error ? err.message : "Could not load provinces and cities."); })
      .finally(() => { if (!cancelled) setLoading((current) => ({ ...current, provinces: false, cities: false })); });
    return () => { cancelled = true; };
  }, [retryKey, token, value.region_code, value.province_code]);

  useEffect(() => {
    if (!value.city_municipality_code) {
      return;
    }
    let cancelled = false;
    getBarangays(token, value.city_municipality_code).then((items) => { if (!cancelled) setBarangays(items); })
      .catch((err: unknown) => { if (!cancelled) setError(err instanceof Error ? err.message : "Could not load barangays."); })
      .finally(() => { if (!cancelled) setLoading((current) => ({ ...current, barangays: false })); });
    return () => { cancelled = true; };
  }, [retryKey, token, value.city_municipality_code]);

  function update(fields: Partial<NewInvestigation>) {
    onChange({ ...value, ...fields });
  }

  return (
    <fieldset className="address-fields">
      <legend>Investigation address</legend>
      <div className="address-fields-grid">
        <label>House/building number<input required maxLength={100} value={value.house_number} onChange={(event) => update({ house_number: event.target.value })} /></label>
        <label>Unit/floor/building name <span className="optional-label">Optional</span><input maxLength={150} value={value.unit_floor_building_name} onChange={(event) => update({ unit_floor_building_name: event.target.value })} /></label>
        <label>Street<input required maxLength={200} value={value.street} onChange={(event) => update({ street: event.target.value })} /></label>
        <label>Subdivision/village/purok <span className="optional-label">Optional</span><input maxLength={200} value={value.subdivision_village_purok} onChange={(event) => update({ subdivision_village_purok: event.target.value })} /></label>
        <label>Region<select required value={value.region_code} disabled={loading.regions} onChange={(event) => {
          const regionCode = event.target.value;
          setError("");
          setProvinces([]); setCities([]); setBarangays([]);
          setLoading((current) => ({ ...current, provinces: Boolean(regionCode), cities: Boolean(regionCode), barangays: false }));
          update({ region_code: regionCode, province_code: "", city_municipality_code: "", barangay_code: "" });
        }}>
          <option value="">{loading.regions ? "Loading regions…" : "Select region"}</option>{regions.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}
        </select></label>
        {provinces.length > 0 && <label>Province <span className="optional-label">Required for provincial locations</span><select required={!cities.length} value={value.province_code} disabled={loading.provinces} onChange={(event) => {
          const provinceCode = event.target.value;
          setError(""); setCities([]); setBarangays([]);
          setLoading((current) => ({ ...current, cities: Boolean(value.region_code), barangays: false }));
          update({ province_code: provinceCode, city_municipality_code: "", barangay_code: "" });
        }}>
          <option value="">{loading.provinces ? "Loading provinces…" : "Select province or independent city"}</option>{provinces.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}
        </select></label>}
        <label>City/municipality<select required value={value.city_municipality_code} disabled={!value.region_code || loading.cities} onChange={(event) => {
          const cityCode = event.target.value;
          setError(""); setBarangays([]); setLoading((current) => ({ ...current, barangays: Boolean(cityCode) }));
          update({ city_municipality_code: cityCode, barangay_code: "" });
        }}>
          <option value="">{loading.cities ? "Loading cities…" : "Select city/municipality"}</option>{cities.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}
        </select></label>
        <label>Barangay<select required value={value.barangay_code} disabled={!value.city_municipality_code || loading.barangays} onChange={(event) => update({ barangay_code: event.target.value })}>
          <option value="">{loading.barangays ? "Loading barangays…" : "Select barangay"}</option>{barangays.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}
        </select></label>
        <label>Postal code <span className="optional-label">Optional</span><input inputMode="numeric" autoComplete="postal-code" maxLength={4} pattern="[0-9]{4}" value={value.postal_code} onChange={(event) => update({ postal_code: event.target.value.replace(/\D/g, "").slice(0, 4) })} /></label>
      </div>
      {error && <p className="error address-data-error" role="alert">{error}</p>}
      {error && <button type="button" className="text-button address-retry" onClick={() => {
        setError(""); setLoading({ regions: true, provinces: Boolean(value.region_code), cities: Boolean(value.region_code), barangays: Boolean(value.city_municipality_code) });
        setRetryKey((key) => key + 1);
      }}>Retry location data</button>}
      {!error && !loading.regions && regions.length === 0 && <p className="muted address-data-error">No regions are available.</p>}
      {!error && value.region_code && !loading.cities && cities.length === 0 && <p className="muted address-data-error">No cities or municipalities are available for this selection.</p>}
      {!error && value.city_municipality_code && !loading.barangays && barangays.length === 0 && <p className="muted address-data-error">No barangays are available for this city or municipality.</p>}
    </fieldset>
  );
}
