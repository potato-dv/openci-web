import type { AgentRosterRow, AgentRoute, AgentShift, AgentShiftInput, User } from "@/types/api";
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

export function getAgents(token: string) {
  return requestJson<User[]>("/users/agents", { token });
}
