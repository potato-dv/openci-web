import { X } from "lucide-react";
import { useCallback, useState } from "react";
import { useSearchParams } from "react-router";

import {
  getActivityLogFilterOptions,
  getActivityLogs,
} from "@/features/activity-logs/api";
import {
  ActivityLogFilters,
} from "@/features/activity-logs/components/ActivityLogFilters";
import { ActivityLogDetailsModal } from "@/features/activity-logs/components/ActivityLogDetailsModal";
import { useResource } from "@/hooks/useResource";
import { PageHeader } from "@/components/layout/PageHeader";
import { ResourceFreshness } from "@/components/data/ResourceFreshness";
import { WorkspaceMobileList, WorkspacePanel } from "@/components/layout/WorkspacePanel";
import { Pagination } from "@/components/data/Pagination";
import { EmptyState, InlineAlert, Skeleton, Button } from "@/components/ui/Primitives";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import type { ActivityLogFilterOptions, ActivityLogItem } from "@/types/api";
import { formatUserName } from "@/utils/userName";
import { date, time } from "@/utils/format";

function humanize(value: string) {
  return value
    .replaceAll(".", " ")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function manilaBoundary(value: string, dayOffset: number) {
  const parsed = new Date(`${value}T00:00:00+08:00`);
  if (Number.isNaN(parsed.getTime())) return "";
  parsed.setUTCDate(parsed.getUTCDate() + dayOffset);
  return parsed.toISOString();
}

function activityQuery(params: URLSearchParams) {
  const query = new URLSearchParams();
  const search = params.get("q")?.trim();
  if (search) query.set("q", search);
  for (const key of ["action", "object_type", "object_id", "sort", "direction", "page", "page_size"]) {
    const value = params.get(key);
    if (value) query.set(key, value);
  }

  const actor = params.get("actor");
  if (actor === "system") query.set("actor_type", "system");
  else if (actor) query.set("actor_id", actor);

  const from = params.get("from");
  if (from) query.set("created_from", manilaBoundary(from, 0));
  const to = params.get("to");
  if (to) query.set("created_to", manilaBoundary(to, 1));
  return query;
}

function formatRecord(item: ActivityLogItem) {
  return item.record_label;
}

function updateSearchParams(
  current: URLSearchParams,
  name: string,
  value: string,
) {
  const next = new URLSearchParams(current);
  if (value) next.set(name, value);
  else next.delete(name);
  if (name !== "page") next.delete("page");
  return next;
}

function AppliedFilterChips({
  params,
  options,
  onRemove,
}: {
  params: URLSearchParams;
  options: ActivityLogFilterOptions | null;
  onRemove: (key: string) => void;
}) {
  const chips: Array<{ key: string; label: string }> = [];
  const search = params.get("q")?.trim();
  if (search) chips.push({ key: "q", label: `Search: ${search}` });
  const action = params.get("action");
  if (action) chips.push({ key: "action", label: `Action: ${humanize(action)}` });
  const actor = params.get("actor");
  if (actor) {
    const actorName = actor === "system"
      ? "System or deleted account"
      : options?.actors.find((item) => String(item.id) === actor)?.name ?? `User ID: ${actor}`;
    chips.push({ key: "actor", label: `Actor: ${actorName}` });
  }
  const objectType = params.get("object_type");
  if (objectType) chips.push({ key: "object_type", label: `Record: ${humanize(objectType)}` });
  const objectId = params.get("object_id");
  if (objectId) chips.push({ key: "object_id", label: `Record ID: ${objectId}` });
  const from = params.get("from");
  if (from) chips.push({ key: "from", label: `From: ${from}` });
  const to = params.get("to");
  if (to) chips.push({ key: "to", label: `To: ${to}` });
  if (!chips.length) return null;

  return (
    <div className="mb-4 flex flex-wrap items-center gap-2" aria-label="Applied filters">
      <span className="text-xs font-medium text-openci-text-muted">Filters:</span>
      {chips.map((chip) => (
        <button
          key={chip.key}
          type="button"
          className="inline-flex min-h-7 items-center gap-1 rounded-full border border-[#d7e2f1] bg-[#f5f8fd] px-2.5 text-xs font-medium text-[#3a5273] transition-colors hover:border-[#b9cae2] hover:bg-[#eef4ff]"
          onClick={() => onRemove(chip.key)}
          aria-label={`Remove ${chip.label}`}
        >
          {chip.label}
          <X size={13} aria-hidden="true" />
        </button>
      ))}
    </div>
  );
}

export function ActivityLogPage({ token }: { token: string }) {
  const [params, setParams] = useSearchParams();
  const [selectedItem, setSelectedItem] = useState<ActivityLogItem | null>(null);
  const query = activityQuery(params);
  const queryKey = query.toString();
  const resource = useResource(
    useCallback(
      (signal) => getActivityLogs(token, new URLSearchParams(queryKey), signal),
      [token, queryKey],
    ),
    {
      resourceKeys: ["activity.logs"],
      refetchOnFocus: true,
      refetchOnReconnect: true,
      staleTimeMs: 60_000,
    },
  );
  const filterOptions = useResource(
    useCallback(
      (signal) => getActivityLogFilterOptions(token, signal),
      [token],
    ),
    {
      refetchOnFocus: true,
      refetchOnReconnect: true,
      staleTimeMs: 5 * 60_000,
    },
  );
  const pageData = resource.data;
  const items = pageData?.items ?? [];
  const pageSize = pageData?.page_size ?? Number(params.get("page_size") ?? 25);

  function updatePage(name: string, value: string) {
    setParams(updateSearchParams(params, name, value), { replace: true });
  }

  function applyFilters(next: URLSearchParams) {
    setParams(next, { replace: true });
  }

  function removeAppliedFilter(key: string) {
    const next = new URLSearchParams(params);
    next.delete(key);
    next.delete("page");
    applyFilters(next);
  }

  return (
    <>
      <PageHeader title="Activity Logs" />
      <WorkspacePanel
        title="Audit trail"
        description={pageData ? `${pageData.total} records` : "Search and review account, investigation, and planning events."}
        action={
          <div className="flex w-full flex-wrap items-center justify-end gap-2 sm:w-auto">
            <ResourceFreshness
              loading={resource.refreshing}
              lastUpdatedAt={resource.lastUpdatedAt}
            />
            <ActivityLogFilters
              appliedParams={params}
              options={filterOptions.data ?? null}
              optionsLoading={filterOptions.loading}
              onApply={applyFilters}
            />
          </div>
        }
      >
        {filterOptions.error && (
          <InlineAlert onRetry={filterOptions.refresh}>
            {filterOptions.error}
          </InlineAlert>
        )}
        {resource.error && (
          <InlineAlert onRetry={resource.refresh}>{resource.error}</InlineAlert>
        )}
        <AppliedFilterChips
          params={params}
          options={filterOptions.data ?? null}
          onRemove={removeAppliedFilter}
        />
        {resource.loading && !pageData ? (
          <Skeleton rows={5} />
        ) : pageData?.items.length ? (
          <>
            <div className="hidden max-w-full overflow-x-auto rounded-lg border border-[#e2e8f1] md:block">
              <Table className="min-w-[1050px] table-fixed">
                <colgroup>
                  <col className="w-[16%]" />
                  <col className="w-[17%]" />
                  <col className="w-[18%]" />
                  <col className="w-[16%]" />
                  <col className="w-[24%]" />
                  <col className="w-[9%]" />
                </colgroup>
                <TableHeader>
                  <TableRow>
                    <TableHead scope="col">When · PHT</TableHead>
                    <TableHead scope="col">Actor</TableHead>
                    <TableHead scope="col">Action</TableHead>
                    <TableHead scope="col">Record</TableHead>
                    <TableHead scope="col">Details</TableHead>
                    <TableHead scope="col" className="text-right">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>
                        <time dateTime={item.created_at} className="grid gap-0.5 whitespace-nowrap">
                          <span>{date(item.created_at)}</span>
                          <span className="text-xs text-openci-text-muted">{time(item.created_at)}</span>
                        </time>
                      </TableCell>
                      <TableCell className="font-medium">
                        {item.actor_name ? formatUserName(item.actor_name) : "System or deleted account"}
                      </TableCell>
                      <TableCell>{humanize(item.action)}</TableCell>
                      <TableCell className="truncate" title={formatRecord(item)}>
                        {formatRecord(item)}
                      </TableCell>
                      <TableCell>
                        <span className="activity-details-text line-clamp-2" title={item.summary}>
                          {item.summary}
                        </span>
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          className="min-h-8! px-2! text-xs!"
                          onClick={() => setSelectedItem(item)}
                        >
                          View details
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <WorkspaceMobileList aria-label="Activity log entries">
              {items.map((item) => (
                <li key={item.id}>
                  <div className="mobile-row-heading">
                    <strong>{item.summary}</strong>
                    <time className="text-xs text-openci-text-muted" dateTime={item.created_at}>
                      {date(item.created_at)}
                    </time>
                  </div>
                  <span className="mobile-row-meta">
                    {item.actor_name ? formatUserName(item.actor_name) : "System or deleted account"} · {formatRecord(item)}
                  </span>
                  <p className="mb-3 text-[13px] text-openci-text">{item.summary}</p>
                  <Button
                    className="min-h-8! px-2! text-xs!"
                    onClick={() => setSelectedItem(item)}
                  >
                    View details
                  </Button>
                </li>
              ))}
            </WorkspaceMobileList>
          </>
        ) : pageData ? (
          <EmptyState title="No activity matches these filters">
            Try changing the search or clearing one of the filters.
          </EmptyState>
        ) : null}
        {pageData && (
          <Pagination
            total={pageData.total}
            page={pageData.page}
            pageSize={pageSize}
            onChange={(page) => updatePage("page", String(page))}
            onSizeChange={(size) => updatePage("page_size", String(size))}
          />
        )}
      </WorkspacePanel>
      <ActivityLogDetailsModal
        item={selectedItem}
        onClose={() => setSelectedItem(null)}
      />
    </>
  );
}
