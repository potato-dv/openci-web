import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import { useCallback, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useSession } from "@/app/session";
import { getAgentRoster } from "@/features/agents/api";
import { getRegions } from "@/features/locations/api";
import { useResource } from "@/hooks/useResource";
import { PageHeader } from "@/components/layout/PageHeader";
import { DataFilterBar, dataFilterFieldClassName } from "@/components/data/DataFilterBar";
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
      <PageHeader
        title="Field Agents"
        description="Set recurring workdays, depot locations, fixed breaks, and dated shift overrides."
        actions={
          <>
            <Button onClick={roster.refresh}>Refresh</Button>
            {user.role === "admin" && (
              <Link className="primary-button" to="/users?new">
                New account
              </Link>
            )}
          </>
        }
      />
      <section className="content-card">
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
          <label className="min-w-[220px] flex-[1_1_220px] md:flex-[0_1_250px]">
            Service region
            <select
              value={region}
              onChange={(event) => update("region", event.target.value)}
            >
              <option value="">All agents, including no shift</option>
              {regions.data?.map((item) => (
                <option value={item.code} key={item.code}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          {user.role === "admin" && (
            <label className={dataFilterFieldClassName}>
              Accounts
              <select
                value={inactive}
                onChange={(event) => update("inactive", event.target.value)}
              >
                <option value="false">Active accounts</option>
                <option value="true">Include inactive</option>
              </select>
            </label>
          )}
        </DataFilterBar>
        {roster.error && (
          <InlineAlert onRetry={roster.refresh}>{roster.error}</InlineAlert>
        )}
        {roster.loading ? (
          <Skeleton />
        ) : roster.data?.length ? (
          <>
            <div className="table-wrap desktop-data">
              <Table className="min-w-[1080px] table-fixed">
                <colgroup>
                  <col className="w-[18%]" />
                  <col className="w-[10%]" />
                  <col className="w-[14%]" />
                  <col className="w-[13%]" />
                  <col className="w-[19%]" />
                  <col className="w-[8%]" />
                  <col className="w-[8%]" />
                  <col className="w-[10%]" />
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
                      <TableCell className="min-w-0">
                        <strong>{row.agent.name}</strong>
                        <small className="block truncate" title={row.agent.email}>{row.agent.email}</small>
                      </TableCell>
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
            <ul
              className="workspace-mobile-list"
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
            </ul>
          </>
        ) : (
          <EmptyState title="No agents match this view">
            Clear the region filter to include agents without a shift.
          </EmptyState>
        )}
      </section>
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
