import { useEffect, useState } from "react";

import { getActivityLogs } from "../services/api";
import type { ActivityLog } from "../types/api";
import { Notice } from "../components/ui/Notice";
import { SectionToolbar } from "../components/layout/SectionToolbar";

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
          {items.map((item) => <tr key={item.id}><td>{new Date(item.created_at).toLocaleString()}</td><td>{item.actor_name ?? "System"}</td><td>{item.action.replaceAll(".", " ")}</td><td>{item.object_type}{item.object_id ? ` #${item.object_id}` : ""}</td><td>{Object.entries(item.details).map(([key, value]) => `${key}: ${String(value)}`).join(" · ") || "—"}</td></tr>)}
        </tbody></table></div>
      )}
    </section>
  );
}
