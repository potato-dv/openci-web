import type { AgentAvailability, AgentRosterRow, AgentRoute, AgentShift, AgentShiftInput, AgentWorkProfile, WeeklySchedule, User } from "@/types/api";
import { requestJson } from "@/services/http";

export function getAgentRoster(
  token: string,
  params: URLSearchParams,
  signal?: AbortSignal,
) {
  return requestJson<AgentRosterRow[]>(`/planning/agent-shifts?${params}`, {
    token,
    signal,
  });
}

export function getManagerAgentRoute(
  token: string,
  agentId: number,
  date: string,
  signal?: AbortSignal,
) {
  return requestJson<AgentRoute>(
    `/planning/agents/${agentId}/route?work_date=${date}`,
    { token, signal },
  );
}

export function saveAgentShift(
  token: string,
  agentId: number,
  shift: AgentShiftInput,
) {
  return requestJson<AgentShift>(
    `/planning/agents/${agentId}/shifts/${shift.work_date}`,
    {
      method: "PUT",
      token,
      body: JSON.stringify(shift),
    },
  );
}

export function getAgentShift(
  token: string,
  agentId: number,
  workDate: string,
) {
  return requestJson<AgentShift | null>(
    `/planning/agents/${agentId}/shifts/${workDate}`,
    { token },
  );
}

export function deleteAgentShiftOverride(token: string, agentId: number, workDate: string) {
  return requestJson<void>(`/planning/agents/${agentId}/shifts/${workDate}`, {
    method: "DELETE",
    token,
  });
}

export function getAgentWorkProfile(token: string, agentId: number, signal?: AbortSignal) {
  return requestJson<AgentWorkProfile | null>(`/planning/agents/${agentId}/work-profile`, { token, signal });
}

export function saveAgentWorkProfile(token: string, agentId: number, profile: AgentWorkProfile) {
  return requestJson<AgentWorkProfile>(`/planning/agents/${agentId}/work-profile`, {
    method: "PUT",
    token,
    body: JSON.stringify(profile),
  });
}

export function getAgentWeeklySchedule(token: string, agentId: number, date: string, signal?: AbortSignal) {
  return requestJson<WeeklySchedule | null>(
    `/planning/agents/${agentId}/weekly-schedule?on_date=${date}`,
    { token, signal },
  );
}

export function saveAgentWeeklySchedule(token: string, agentId: number, schedule: WeeklySchedule) {
  return requestJson<WeeklySchedule>(`/planning/agents/${agentId}/weekly-schedule`, {
    method: "PUT",
    token,
    body: JSON.stringify(schedule),
  });
}

export function getAgentAvailability(token: string, agentId: number, fromDate: string, toDate: string, signal?: AbortSignal) {
  const params = new URLSearchParams({ from_date: fromDate, to_date: toDate });
  return requestJson<AgentAvailability>(`/planning/agents/${agentId}/availability?${params}`, { token, signal });
}

export function getAgents(token: string, signal?: AbortSignal) {
  return requestJson<User[]>("/users/agents", { token, signal });
}
