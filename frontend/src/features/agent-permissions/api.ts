import { requestJson } from "@/services/http";
import type {
  AgentFeatureCode,
  AgentPermissionEffect,
  AgentPermissionHistoryItem,
  AgentPermissionState,
  AgentPermissions,
} from "@/types/api";

export const DEFAULT_AGENT_PERMISSIONS: AgentPermissions = {
  "investigation.request_revisit": true,
  "route.view_own_history": true,
  "investigation.view_own_history": false,
};

export function getMyAgentPermissions(token: string) {
  return requestJson<{ permissions: AgentPermissions }>(
    "/users/me/agent-permissions",
    { token },
  );
}

export function getAgentPermissionCatalog(token: string, signal?: AbortSignal) {
  return requestJson<{
    features: Omit<AgentPermissionState["features"][number], "override" | "effective_allowed">[];
    mandatory_workflows: AgentPermissionState["mandatory_workflows"];
  }>("/agent-permissions/catalog", { token, signal });
}

export function getAgentPermissionState(token: string, agentId: number, signal?: AbortSignal) {
  return requestJson<AgentPermissionState>(
    `/users/${agentId}/agent-permissions`,
    { token, signal },
  );
}

export function saveAgentPermissionState(
  token: string,
  agentId: number,
  overrides: Record<AgentFeatureCode, AgentPermissionEffect>,
) {
  return requestJson<AgentPermissionState>(
    `/users/${agentId}/agent-permissions`,
    { method: "PUT", token, body: JSON.stringify({ overrides }) },
  );
}

export function getAgentPermissionHistory(token: string, agentId: number, signal?: AbortSignal) {
  return requestJson<{
    items: AgentPermissionHistoryItem[];
    total: number;
    limit: number;
    offset: number;
  }>(`/users/${agentId}/agent-permissions/history?limit=50`, { token, signal });
}
