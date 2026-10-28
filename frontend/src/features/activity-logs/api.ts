import type { ActivityLog } from "@/types/api";
import { requestJson } from "@/services/http";

export function getActivityLogs(token: string) {
  return requestJson<ActivityLog[]>("/activity-logs/", { token });
}
