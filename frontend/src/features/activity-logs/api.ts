import type {
  ActivityLogFilterOptions,
  ActivityLogPage,
} from "@/types/api";
import { requestJson } from "@/services/http";

export function getActivityLogs(
  token: string,
  params: URLSearchParams,
  signal?: AbortSignal,
) {
  const query = params.toString();
  return requestJson<ActivityLogPage>(
    `/activity-logs/query${query ? `?${query}` : ""}`,
    { token, signal },
  );
}

export function getActivityLogFilterOptions(
  token: string,
  signal?: AbortSignal,
) {
  return requestJson<ActivityLogFilterOptions>("/activity-logs/filter-options", {
    token,
    signal,
  });
}
