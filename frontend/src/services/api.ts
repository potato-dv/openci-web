import type {
  ActivityLog,
  Assignment,
  Investigation,
  InvestigationUpdate,
  LocationOption,
  LoginResponse,
  NewInvestigation,
  NewUser,
  Report,
  ReportInput,
  Review,
  User,
} from "../types/api";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

type RequestOptions = RequestInit & {
  token?: string;
};

async function requestJson<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const headers = new Headers(options.headers);

  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (options.token) {
    headers.set("Authorization", `Bearer ${options.token}`);
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });

  const contentType = response.headers.get("content-type") ?? "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : null;

  if (!response.ok) {
    const detail =
      typeof data?.detail === "string"
        ? data.detail
        : Array.isArray(data?.detail)
          ? data.detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join("; ")
        : "The request could not be completed.";
    throw new Error(detail);
  }

  return data as T;
}

export function login(email: string, password: string) {
  return requestJson<LoginResponse>("/users/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function getProfile(token: string) {
  return requestJson<User>("/users/me", { token });
}

export function getInvestigations(token: string) {
  return requestJson<Investigation[]>("/investigations/", { token });
}

export function getUsers(token: string) {
  return requestJson<User[]>("/users/", { token });
}

export function createUser(token: string, user: NewUser) {
  return requestJson<User>("/users/", {
    method: "POST",
    token,
    body: JSON.stringify(user),
  });
}

export function updateUserActivation(
  token: string,
  userId: number,
  isActive: boolean,
) {
  return requestJson<User>(`/users/${userId}/activation`, {
    method: "PATCH",
    token,
    body: JSON.stringify({ is_active: isActive }),
  });
}

export function updateUserRole(token: string, userId: number, role: User["role"]) {
  return requestJson<User>(`/users/${userId}/role`, {
    method: "PATCH",
    token,
    body: JSON.stringify({ role }),
  });
}

export function getRegions(token: string) {
  return requestJson<LocationOption[]>("/locations/regions", { token });
}

export function getProvinces(token: string, regionCode: string) {
  return requestJson<LocationOption[]>(`/locations/regions/${regionCode}/provinces`, { token });
}

export function getCities(token: string, regionCode: string, provinceCode?: string) {
  const query = provinceCode ? `?province_code=${provinceCode}` : "";
  return requestJson<LocationOption[]>(`/locations/regions/${regionCode}/cities-municipalities${query}`, { token });
}

export function getBarangays(token: string, cityCode: string) {
  return requestJson<LocationOption[]>(`/locations/cities-municipalities/${cityCode}/barangays`, { token });
}

export function getActivityLogs(token: string) {
  return requestJson<ActivityLog[]>("/activity-logs/", { token });
}

export function getAgents(token: string) {
  return requestJson<User[]>("/users/agents", { token });
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
      subdivision_village_purok: investigation.subdivision_village_purok || null,
      province_code: investigation.province_code || null,
      postal_code: investigation.postal_code || null,
    }),
  });
}

export function updateInvestigation(token: string, investigationId: number, values: InvestigationUpdate) {
  return requestJson<Investigation>(`/investigations/${investigationId}`, {
    method: "PATCH", token, body: JSON.stringify(values),
  });
}

export function deleteInvestigation(token: string, investigationId: number) {
  return requestJson<{ message: string }>(`/investigations/${investigationId}`, { method: "DELETE", token });
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

export function getAssignments(token: string, investigationId: number) {
  return requestJson<Assignment[]>(
    `/investigations/${investigationId}/assignments`,
    { token },
  );
}

export function getReport(token: string, investigationId: number) {
  return requestJson<Report | null>(`/investigations/${investigationId}/report`, {
    token,
  });
}

export function getReportVersions(token: string, investigationId: number) {
  return requestJson<Report[]>(`/investigations/${investigationId}/reports`, {
    token,
  });
}

export function saveReport(
  token: string,
  investigationId: number,
  report: ReportInput,
) {
  return requestJson<Report>(`/investigations/${investigationId}/report`, {
    method: "PUT",
    token,
    body: JSON.stringify(report),
  });
}

export function submitReport(token: string, investigationId: number) {
  return requestJson<Report>(
    `/investigations/${investigationId}/report/submit`,
    {
      method: "POST",
      token,
    },
  );
}

export function getReviews(token: string, investigationId: number) {
  return requestJson<Review[]>(`/investigations/${investigationId}/reviews`, {
    token,
  });
}

export function reviewReport(
  token: string,
  investigationId: number,
  decision: Review["decision"],
  comments?: string,
) {
  return requestJson<Review>(`/investigations/${investigationId}/reviews`, {
    method: "POST",
    token,
    body: JSON.stringify({ decision, comments }),
  });
}
