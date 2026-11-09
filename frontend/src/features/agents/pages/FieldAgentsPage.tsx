import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import { useCallback, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { RefreshCw, Plus } from "lucide-react";
import { useSession } from "@/app/session";
import { getAgentRoster } from "@/features/agents/api";
import { getRegions } from "@/features/locations/api";
import { useResource } from "@/hooks/useResource";
import { PageHeader } from "@/components/layout/PageHeader";
import { ResourceFreshness } from "@/components/data/ResourceFreshness";
import { WorkspaceMobileList, WorkspacePanel } from "@/components/layout/WorkspacePanel";
import { DataFilterBar, dataFilterFieldClassName } from "@/components/data/DataFilterBar";
import { WorkspaceSelect } from "@/components/ui/WorkspaceSelect";
import { PersonIdentity } from "@/components/data/PersonIdentity";
import { AgentShiftDrawer } from "@/features/agents/components/AgentShiftDrawer";
import {
  Button,
  EmptyState,
  InlineAlert,
  Skeleton,
  ToastRegion,
} from "@/components/ui/Primitives";
import { manilaToday, time } from "@/utils/format";
import type { AgentRosterRow } from "@/types/api";

function shiftStatusLabel(row: AgentRosterRow): string {
  const status = row.availability_day?.status;
  if (status === "shift_ended") return "Shift ended";
  if (status === "day_off") return "Day off";
  if (status === "not_configured") return "Not configured";
  if (row.shift) {
    if (row.shift.is_available) return "Available";
    return status === "scheduled" ? "Scheduled · unavailable" : "Unavailable";
  }
  return row.availability_day?.is_available ? "Scheduled" : "No shift";
}

export function FieldAgentsPage() {
  const { token, user } = useSession();
  const [params, setParams] = useSearchParams();
  const date = params.get("date") ?? manilaToday();
  const region = params.get("region") ?? "";
  const inactive = params.get("inactive") ?? "false";
  const [selected, setSelected] = useState<AgentRosterRow | null>(null);
  const [message, setMessage] = useState("");
  const regions = useResource(useCallback(() => getRegions(token), [token]));
  const roster = useResource(
    useCallback(
      (signal) =>
        getAgentRoster(
          token,
          new URLSearchParams({
            work_date: date,
            ...(region ? { region_code: region } : {}),
            include_inactive: inactive,
          }),
          signal,
        ),
      [token, date, region, inactive],
    ),
    {
      resourceKeys: ["users.list", "schedules.list", "route.planning"],
      refetchOnFocus: true,
      refetchOnReconnect: true,
      staleTimeMs: 60_000,
    },
  );
  const selectedRow =
    selected && roster.data
      ? (roster.data.find((item) => item.agent.id === selected.agent.id) ??
        selected)
      : selected;
  function update(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  }
  return (
    <>
      <PageHeader title="Field Agents" />
      <WorkspacePanel
        title="Daily roster"
        description="Account status, shift availability, and assigned workload stay separate."
        action={
          <div className="flex w-full flex-wrap items-center justify-end gap-2 sm:w-auto">
            <ResourceFreshness
              loading={roster.refreshing}
              lastUpdatedAt={roster.lastUpdatedAt}
            />
            <Button onClick={roster.refresh} disabled={roster.refreshing}>
              <RefreshCw
                className={roster.refreshing ? "animate-spin" : ""}
                size={16}
                aria-hidden="true"
              />
              Refresh
            </Button>
            {user.role === "admin" && (
              <Link className="primary-button" to="/users?new">
                <Plus size={16} aria-hidden="true" />
                New account
              </Link>
            )}
          </div>
        }
      >
        {regions.error && (
          <InlineAlert onRetry={regions.refresh}>{regions.error}</InlineAlert>
        )}
        <DataFilterBar>
          <label className={dataFilterFieldClassName}>
            Work date
            <input
              type="date"
              value={date}
              onChange={(event) => update("date", event.target.value)}
            />
          </label>
          <WorkspaceSelect
            className="min-w-[220px] flex-[1_1_220px] md:flex-[0_1_250px]"
            label="Service region"
            value={region}
            onValueChange={(value) => update("region", value)}
            options={[{ value: "", label: "All agents, including no shift" }, ...(regions.data?.map((item) => ({ value: item.code, label: item.name })) ?? [])]}
          />
          {user.role === "admin" && (
            <WorkspaceSelect
              className={dataFilterFieldClassName}
              label="Accounts"
              value={inactive}
              onValueChange={(value) => update("inactive", value)}
              options={[{ value: "false", label: "Active accounts" }, { value: "true", label: "Include inactive" }]}
            />
          )}
        </DataFilterBar>
        {roster.error && (
          <InlineAlert onRetry={roster.refresh}>{roster.error}</InlineAlert>
        )}
        {roster.loading && !roster.data ? (
          <Skeleton />
        ) : roster.data?.length ? (
          <>
            <div className="hidden max-w-full overflow-x-auto rounded-lg border border-[#e2e8f1] md:block">
              <Table className="min-w-[980px] table-fixed">
                <colgroup>
                  <col className="w-[17%]" />
                  <col className="w-[9%]" />
                  <col className="w-[13%]" />
                  <col className="w-[12%]" />
                  <col className="w-[18%]" />
                  <col className="w-[9%]" />
                  <col className="w-[8%]" />
                  <col className="w-[14%]" />
                </colgroup>
                <TableHeader>
                  <TableRow>
                    <TableHead scope="col">Agent</TableHead>
                    <TableHead scope="col">Account</TableHead>
                    <TableHead scope="col">Availability</TableHead>
                    <TableHead scope="col">Hours · PHT</TableHead>
                    <TableHead scope="col">Starting point</TableHead>
                    <TableHead scope="col" className="text-right">Visit limit</TableHead>
                    <TableHead scope="col" className="text-right">Open cases</TableHead>
                    <TableHead scope="col" className="text-right">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {roster.data.map((row) => (
                    <TableRow key={row.agent.id}>
                      <TableCell className="min-w-0"><PersonIdentity name={row.agent.name} detail={row.agent.email} /></TableCell>
                      <TableCell>
                        <span
                          className={`status-badge account-${row.agent.is_active ? "active" : "inactive"}`}
                        >
                          {row.agent.is_active ? "Active" : "Inactive"}
                        </span>
                      </TableCell>
                      <TableCell>
                        {shiftStatusLabel(row)}
                        {row.shift?.source === "manual" && (
                          <small className="block">Manual override</small>
                        )}
                      </TableCell>
                      <TableCell className="nowrap">
                        {row.shift
                          ? `${time(row.shift.shift_starts_at)}–${time(row.shift.shift_ends_at)}`
                          : row.availability_day?.shift_starts_at &&
                              row.availability_day.shift_ends_at
                            ? `${time(row.availability_day.shift_starts_at)}–${time(row.availability_day.shift_ends_at)}`
                            : "—"}
                      </TableCell>
                      <TableCell className="location-cell">
                        {row.shift?.start_location_label ||
                          (row.shift
                            ? `${row.shift.start_latitude.toFixed(5)}, ${row.shift.start_longitude.toFixed(5)}`
                            : row.availability_day?.start_latitude != null &&
                                row.availability_day.start_longitude != null
                              ? `${row.availability_day.start_latitude.toFixed(5)}, ${row.availability_day.start_longitude.toFixed(5)}`
                              : row.work_profile_set
                                ? "Depot configured"
                                : "Not configured")}
                      </TableCell>
                      <TableCell className="text-right">{row.shift?.max_visits ?? "—"}</TableCell>
                      <TableCell className="text-right">{row.assigned_workload_count}</TableCell>
                      <TableCell className="text-right">
                        <Button onClick={() => setSelected(row)}>
                          View agent
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <WorkspaceMobileList
              aria-label="Field agent roster"
            >
              {roster.data.map((row) => (
                <li key={row.agent.id}>
                  <div className="mobile-row-heading">
                    <strong>{row.agent.name}</strong>
                    <span
                      className={`status-badge account-${row.agent.is_active ? "active" : "inactive"}`}
                    >
                      Account {row.agent.is_active ? "active" : "inactive"}
                    </span>
                  </div>
                  <span className="mobile-row-meta">{row.agent.email}</span>
                  <dl className="mobile-row-facts">
                    <div>
                      <dt>Shift</dt>
                      <dd>{shiftStatusLabel(row)}</dd>
                    </div>
                    <div>
                      <dt>Hours · PHT</dt>
                      <dd>
                        {row.shift
                          ? `${time(row.shift.shift_starts_at)}–${time(row.shift.shift_ends_at)}`
                          : row.availability_day?.shift_starts_at &&
                              row.availability_day.shift_ends_at
                            ? `${time(row.availability_day.shift_starts_at)}–${time(row.availability_day.shift_ends_at)}`
                            : "—"}
                      </dd>
                    </div>
                    <div>
                      <dt>Starting point</dt>
                      <dd>
                        {row.shift?.start_location_label ||
                          (row.shift
                            ? `${row.shift.start_latitude.toFixed(5)}, ${row.shift.start_longitude.toFixed(5)}`
                            : row.availability_day?.start_latitude != null &&
                                row.availability_day.start_longitude != null
                              ? `${row.availability_day.start_latitude.toFixed(5)}, ${row.availability_day.start_longitude.toFixed(5)}`
                              : row.work_profile_set
                                ? "Depot configured"
                                : "Not configured")}
                      </dd>
                    </div>
                    <div>
                      <dt>Open cases / limit</dt>
                      <dd>
                        {row.assigned_workload_count} /{" "}
                        {row.shift?.max_visits ?? "Not set"}
                      </dd>
                    </div>
                  </dl>
                  <Button
                    onClick={() => setSelected(row)}
                    aria-label={`View agent ${row.agent.name}`}
                  >
                    View agent
                  </Button>
                </li>
              ))}
            </WorkspaceMobileList>
          </>
        ) : (
          <EmptyState title="No agents match this view">
            Clear the region filter to include agents without a shift.
          </EmptyState>
        )}
      </WorkspacePanel>
      {selectedRow && (
        <AgentShiftDrawer
          key={`${selectedRow.agent.id}:${date}`}
          token={token}
          date={date}
          row={selectedRow}
          regions={regions.data ?? []}
          onClose={() => setSelected(null)}
          onUpdated={roster.refresh}
          onSaved={() => {
            setSelected(null);
            roster.refresh();
            setMessage("Agent shift saved.");
          }}
        />
      )}
      <ToastRegion message={message} onDismiss={() => setMessage("")} />
    </>
  );
}
