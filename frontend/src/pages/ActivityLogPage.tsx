import { useEffect, useState } from "react";

import { getActivityLogs } from "../services/api";
import type { ActivityLog } from "../types/api";
import { Notice } from "../components/ui/Notice";
import { SectionToolbar } from "../components/layout/SectionToolbar";
import { formatUserName } from "../utils/userName";

function humanize(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatDetailValue(value: unknown): string {
  if (value === null || value === undefined) return "None";
  if (Array.isArray(value)) return value.map(String).join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function formatActivityDetails(item: ActivityLog) {
  const details = item.details ?? {};

  if (item.action === "user.created" && typeof details.role === "string") {
    return `Account created with ${humanize(details.role)} role`;
  }
  if (item.action === "user.activation_changed" && typeof details.is_active === "boolean") {
    return `Account ${details.is_active ? "activated" : "deactivated"}`;
  }
  if (item.action === "user.role_changed" && typeof details.from === "string" && typeof details.to === "string") {
    return `Role changed from ${humanize(details.from)} to ${humanize(details.to)}`;
  }
  if (item.action === "investigation.assigned" && details.agent_id !== undefined) {
    return `Assigned agent ID: ${formatDetailValue(details.agent_id)}`;
  }
  if (item.action === "report.reviewed" && typeof details.decision === "string") {
    return `Review decision: ${humanize(details.decision)}`;
  }
  if (item.action === "investigation.updated" && Array.isArray(details.fields)) {
    return details.fields.length
      ? `Updated fields: ${details.fields.map((field) => humanize(String(field))).join(", ")}`
      : "Investigation updated";
  }

  const entries = Object.entries(details);
  if (entries.length === 0) return "No additional details";
  return entries.map(([key, value]) => `${humanize(key)}: ${formatDetailValue(value)}`).join(" · ");
}

export function ActivityLogPage({ token }: { token: string }) {
  const [items, setItems] = useState<ActivityLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getActivityLogs(token)
      .then((data) => { if (!cancelled) setItems(data); })
      .catch((err: unknown) => { if (!cancelled) setError(err instanceof Error ? err.message : "Could not load activity."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [refresh, token]);

  return (
    <section className="content-card">
      <SectionToolbar title="System activity" description="Recent account and investigation changes." actions={<button className="secondary-button toolbar-button" onClick={() => { setLoading(true); setError(""); setRefresh((value) => value + 1); }} disabled={loading}>Refresh</button>} />
      {error && <Notice message={error} actionLabel="Retry" onAction={() => { setLoading(true); setError(""); setRefresh((value) => value + 1); }} />}
      {loading ? <p className="muted">Loading activity…</p> : items.length === 0 ? <p className="empty-state">No activity recorded yet.</p> : (
        <div className="table-wrap"><table><thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Record</th><th>Details</th></tr></thead><tbody>
          {items.map((item) => {
            const details = formatActivityDetails(item);
            return (
              <tr key={item.id}>
                <td>{new Date(item.created_at).toLocaleString()}</td>
                <td>{item.actor_name ? formatUserName(item.actor_name) : "System"}</td>
                <td>{item.action.replaceAll(".", " ")}</td>
                <td>{item.object_type}{item.object_id ? ` #${item.object_id}` : ""}</td>
                <td><span className="activity-details-text" title={details}>{details}</span></td>
              </tr>
            );
          })}
        </tbody></table></div>
      )}
    </section>
  );
}
