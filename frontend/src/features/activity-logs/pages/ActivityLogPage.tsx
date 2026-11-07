import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";

import { getActivityLogs } from "@/features/activity-logs/api";
import type { ActivityLog } from "@/types/api";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/card";
import { Button, EmptyState, InlineAlert, Skeleton } from "@/components/ui/Primitives";
import { formatUserName } from "@/utils/userName";
import { date, time } from "@/utils/format";

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

  function reload() {
    setLoading(true);
    setError("");
    setRefresh((value) => value + 1);
  }

  useEffect(() => {
    let cancelled = false;
    getActivityLogs(token)
      .then((data) => { if (!cancelled) setItems(data); })
      .catch((err: unknown) => { if (!cancelled) setError(err instanceof Error ? err.message : "Could not load activity."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [refresh, token]);

  return (
    <>
      <PageHeader
        title="Activity Logs"
        description="Recent account and investigation changes. Times are shown in Philippine time."
        actions={
          <Button onClick={reload} disabled={loading}>
            <RefreshCw size={16} aria-hidden="true" />
            Refresh
          </Button>
        }
      />
      <Card className="content-card">
        {error && <InlineAlert onRetry={reload}>{error}</InlineAlert>}
        {loading ? (
          <Skeleton rows={5} />
        ) : items.length === 0 ? (
          <EmptyState title="No activity recorded yet">
            Account and investigation changes will appear here.
          </EmptyState>
        ) : (
          <>
          <div className="table-wrap desktop-data">
            <Table className="min-w-[850px] table-fixed">
              <colgroup>
                <col className="w-[17%]" />
                <col className="w-[17%]" />
                <col className="w-[21%]" />
                <col className="w-[15%]" />
                <col className="w-[30%]" />
              </colgroup>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">When · PHT</TableHead>
                  <TableHead scope="col">Actor</TableHead>
                  <TableHead scope="col">Action</TableHead>
                  <TableHead scope="col">Record</TableHead>
                  <TableHead scope="col">Details</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => {
                  const details = formatActivityDetails(item);
                  return (
                    <TableRow key={item.id}>
                      <TableCell>
                        <time dateTime={item.created_at} className="grid gap-0.5 whitespace-nowrap">
                          <span>{date(item.created_at)}</span>
                          <span className="text-xs text-openci-text-muted">{time(item.created_at)}</span>
                        </time>
                      </TableCell>
                      <TableCell className="font-medium">{item.actor_name ? formatUserName(item.actor_name) : "System"}</TableCell>
                      <TableCell className="capitalize">{item.action.replaceAll(".", " ")}</TableCell>
                      <TableCell className="truncate" title={`${item.object_type}${item.object_id ? ` #${item.object_id}` : ""}`}>
                        {humanize(item.object_type)}{item.object_id ? ` #${item.object_id}` : ""}
                      </TableCell>
                      <TableCell><span className="activity-details-text line-clamp-2" title={details}>{details}</span></TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
          <ul className="workspace-mobile-list" aria-label="Activity log entries">
            {items.map((item) => {
              const details = formatActivityDetails(item);
              return (
                <li key={item.id}>
                  <div className="mobile-row-heading">
                    <strong className="capitalize">{item.action.replaceAll(".", " ")}</strong>
                    <time className="text-xs text-openci-text-muted" dateTime={item.created_at}>{date(item.created_at)}</time>
                  </div>
                  <span className="mobile-row-meta">{item.actor_name ? formatUserName(item.actor_name) : "System"} · {humanize(item.object_type)}{item.object_id ? ` #${item.object_id}` : ""}</span>
                  <p className="mb-0 text-[13px] text-openci-text">{details}</p>
                </li>
              );
            })}
          </ul>
          </>
        )}
      </Card>
    </>
  );
}
