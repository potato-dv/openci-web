import type {
  Assignment,
  GeocodeCandidate,
  Investigation,
  InvestigationLocation,
  InvestigationPage,
  InvestigationUpdate,
  NewInvestigation,
} from "@/types/api";
import { requestJson } from "@/services/http";

export function getInvestigations(
  token: string,
  params: URLSearchParams = new URLSearchParams(),
  signal?: AbortSignal,
) {
  return requestJson<InvestigationPage>(`/investigations/?${params}`, {
    token,
    signal,
  });
}

export function getInvestigation(
  token: string,
  id: number,
  signal?: AbortSignal,
) {
  return requestJson<Investigation>(`/investigations/${id}`, { token, signal });
}

export function getTrashedInvestigations(token: string) {
  return requestJson<Investigation[]>("/investigations/trash", { token });
}

export function createInvestigation(
  token: string,
  investigation: NewInvestigation,
) {
  return requestJson<Investigation>("/investigations/", {
    method: "POST",
    token,
    body: JSON.stringify({
      ...investigation,
      unit_floor_building_name: investigation.unit_floor_building_name || null,
      subdivision_village_purok:
        investigation.subdivision_village_purok || null,
      province_code: investigation.province_code || null,
      postal_code: investigation.postal_code || null,
    }),
  });
}

export function updateInvestigation(
  token: string,
  investigationId: number,
  values: InvestigationUpdate,
) {
  return requestJson<Investigation>(`/investigations/${investigationId}`, {
    method: "PATCH",
    token,
    body: JSON.stringify(values),
  });
}

export function deleteInvestigation(token: string, investigationId: number) {
  return requestJson<{ message: string }>(
    `/investigations/${investigationId}`,
    { method: "DELETE", token },
  );
}

export function permanentlyDeleteInvestigation(
  token: string,
  investigationId: number,
) {
  return requestJson<void>(`/investigations/${investigationId}/permanent`, {
    method: "DELETE",
    token,
  });
}

export function restoreInvestigation(token: string, investigationId: number) {
  return requestJson<Investigation>(
    `/investigations/${investigationId}/restore`,
    { method: "POST", token },
  );
}

export function assignInvestigation(
  token: string,
  investigationId: number,
  agentId: number,
  note?: string,
) {
  return requestJson<Assignment>(`/investigations/${investigationId}/assign`, {
    method: "POST",
    token,
    body: JSON.stringify({ agent_id: agentId, note }),
  });
}

export function retryInvestigationRoute(token: string, investigationId: number) {
  return requestJson<Assignment>(
    `/investigations/${investigationId}/route-refresh`,
    { method: "POST", token },
  );
}

export function getGeocodeSuggestions(token: string, investigationId: number) {
  return requestJson<GeocodeCandidate[]>(
    `/investigations/${investigationId}/geocode-suggestions`,
    { token },
  );
}

export function getInvestigationLocation(
  token: string,
  investigationId: number,
) {
  return requestJson<InvestigationLocation | null>(
    `/investigations/${investigationId}/location`,
    { token },
  );
}

export function confirmInvestigationLocation(
  token: string,
  investigationId: number,
  values: Pick<
    InvestigationLocation,
    "latitude" | "longitude" | "source" | "provider_ref"
  >,
) {
  return requestJson<Investigation>(
    `/investigations/${investigationId}/location`,
    {
      method: "PUT",
      token,
      body: JSON.stringify(values),
    },
  );
}

export function getAssignments(token: string, investigationId: number) {
  return requestJson<Assignment[]>(
    `/investigations/${investigationId}/assignments`,
    { token },
  );
}
