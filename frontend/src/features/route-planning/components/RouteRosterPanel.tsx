import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { MapPin, MapPinOff, Search, Users } from "lucide-react";
import type { PlanningMapData, PlanningRouteOverviewAgent } from "@/types/api";
import type {
  MapAgent,
  MapInvestigation,
  MapSelection,
} from "@/components/map/mapTypes";
import { EmptyState, Tabs } from "@/components/ui/Primitives";
import { duration, time } from "@/utils/format";
import {
  planningReasonCopy,
  planningStatusLabel,
  routeStatusLabel,
} from "./publishedRouteData";

type RosterTab = "investigations" | "agents" | "confirmation";
type PriorityFilter = "all" | "urgent" | "high" | "normal";
type StatusFilter = "all" | string;

type Props = {
  agents: MapAgent[];
  investigations: MapInvestigation[];
  issues: PlanningMapData | null;
  routeAgents: PlanningRouteOverviewAgent[];
  selection: MapSelection;
  date: string;
  headerAction?: ReactNode;
  loading?: boolean;
  onSelect: (selection: MapSelection) => void;
};

const rosterClasses = {
  root: "route-roster min-w-0",
  heading:
    "route-roster-heading sticky top-0 z-10 flex items-start justify-between gap-3 border-b border-openci-border bg-white px-4 py-3",
  headingCopy: "grid min-w-0 flex-1 gap-1",
  headingTitle: "mb-0! text-sm! font-semibold! leading-snug!",
  headingDescription: "text-xs leading-relaxed text-openci-text-muted",
  search:
    "route-roster-search mx-4 mt-3 flex! min-h-10 items-center gap-2! rounded-md border border-openci-border-strong bg-white px-3 text-openci-text-muted focus-within:border-openci-accent focus-within:ring-2 focus-within:ring-openci-accent/20",
  searchInput:
    "h-9! min-h-0! w-0! min-w-0 flex-1 border-0! bg-transparent! px-0! py-0! text-xs! outline-none! focus:border-0!",
  section: "route-roster-list-section min-w-0",
  filters: "route-roster-filters grid gap-2 px-4 py-2.5",
  filter: "grid gap-1 text-xs font-medium text-openci-text-muted",
  filterControl: "h-9! min-h-9! w-full px-2.5! py-1! text-xs!",
  caption:
    "route-list-caption flex items-center justify-between gap-2 border-t border-openci-border px-4 py-2 text-xs text-openci-text-muted",
  items:
    "route-roster-items m-0 grid list-none divide-y divide-openci-border p-0",
  item: "route-roster-item flex w-full min-w-0 items-start gap-2 border-0 bg-transparent px-4 py-2.5 text-left text-openci-text no-underline transition-colors hover:bg-openci-surface-muted focus-visible:relative [&[aria-pressed=true]]:bg-openci-surface-selected",
  itemMain: "route-roster-item-main grid min-w-0 flex-1 gap-0.5",
  itemTopline:
    "route-roster-item-topline flex min-w-0 flex-wrap items-start justify-between gap-1",
  confirmationTopline:
    "route-roster-item-topline grid min-w-0 justify-items-start gap-1",
  itemTitle:
    "route-roster-item-title min-w-0 break-all text-xs font-semibold text-openci-accent-strong",
  address:
    "route-roster-address break-words text-xs leading-snug text-openci-text-muted",
  metadata:
    "route-roster-item-meta flex min-w-0 flex-wrap gap-x-2 gap-y-1 text-[11px] leading-snug text-openci-text-muted",
  priorityBadge: "shrink-0 rounded px-1.5 py-0.5 text-[10px] capitalize",
  icon: "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border",
  emptyFilter:
    "route-roster-empty-filter mx-4 my-2 rounded-md bg-openci-surface-muted p-2 text-xs text-openci-text-muted",
  manageShifts:
    "route-roster-manage-shifts mx-4 mt-3 grid gap-2 rounded-md border border-openci-border bg-openci-surface-muted p-3 text-xs text-openci-text-muted",
};

function matches(
  query: string,
  ...values: (string | number | null | undefined)[]
) {
  const value = query.trim().toLocaleLowerCase();
  return (
    !value ||
    values.some((item) =>
      String(item ?? "")
        .toLocaleLowerCase()
        .includes(value),
    )
  );
}

export function RouteRosterPanel({
  agents,
  investigations,
  issues,
  routeAgents,
  selection,
  date,
  headerAction,
  loading = false,
  onSelect,
}: Props) {
  const [tab, setTab] = useState<RosterTab>("investigations");
  const [query, setQuery] = useState("");
  const [priorityFilter, setPriorityFilter] = useState<PriorityFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const routeAgentById = useMemo(
    () => new Map(routeAgents.map((agent) => [agent.id, agent])),
    [routeAgents],
  );
  const mappedAgentIds = useMemo(
    () => new Set(agents.map((agent) => agent.id)),
    [agents],
  );
  const mappedAgentById = useMemo(
    () => new Map(agents.map((agent) => [agent.id, agent])),
    [agents],
  );
  const filteredAgents = (issues?.agents ?? []).filter((agent) =>
    matches(query, agent.name, agent.region_code),
  );
  const unlocatedInvestigations = issues?.unlocated_investigations ?? [];
  const unlocatedAgents = issues?.unlocated_agents ?? [];
  const confirmationCount = unlocatedInvestigations.length;
  const investigationStatuses = useMemo(
    () => [...new Set(investigations.map((item) => item.status))].sort(),
    [investigations],
  );
  const filteredInvestigations = useMemo(
    () =>
      investigations.filter(
        (item) =>
          matches(
            query,
            item.reference_number,
            item.address_display,
            item.agent_name,
            item.status,
            item.priority,
          ) &&
          (priorityFilter === "all" || item.priority === priorityFilter) &&
          (statusFilter === "all" || item.status === statusFilter),
      ),
    [investigations, priorityFilter, query, statusFilter],
  );

  return (
    <div className={rosterClasses.root}>
      <div className={rosterClasses.heading}>
        <div className={rosterClasses.headingCopy}>
          <h2 className={rosterClasses.headingTitle}>Planning records</h2>
          <span className={rosterClasses.headingDescription}>
            Search investigations, agents, and locations that need confirmation.
          </span>
        </div>
        {headerAction}
      </div>

      <Tabs
        label="Planning records"
        value={tab}
        onChange={(value) => setTab(value as RosterTab)}
        items={[
          {
            value: "investigations",
            label: (
              <span className="grid justify-items-center gap-0.5">
                <span>Investigations</span>{" "}
                <span className="tabular-nums">{investigations.length}</span>
              </span>
            ),
          },
          {
            value: "agents",
            label: (
              <span className="grid justify-items-center gap-0.5">
                <span>Agents</span>{" "}
                <span className="tabular-nums">
                  {issues?.agents.length ?? agents.length}
                </span>
              </span>
            ),
          },
          {
            value: "confirmation",
            label: (
              <span className="grid justify-items-center gap-0.5">
                <span>Needs confirmation</span>{" "}
                <span className="tabular-nums">{confirmationCount}</span>
              </span>
            ),
          },
        ]}
      />

      <label className={rosterClasses.search}>
        <Search className="shrink-0" size={16} aria-hidden="true" />
        <input
          className={rosterClasses.searchInput}
          aria-label="Search planning records"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={
            tab === "agents"
              ? "Search by agent name…"
              : "Search reference, address, or name…"
          }
        />
      </label>

      {tab === "investigations" && (
        <section className={rosterClasses.section} aria-label="Investigations">
          <div
            className={rosterClasses.filters}
            aria-label="Filter investigations"
          >
            <label className={rosterClasses.filter}>
              <span>Priority</span>
              <select
                className={rosterClasses.filterControl}
                aria-label="Filter investigations by priority"
                value={priorityFilter}
                onChange={(event) =>
                  setPriorityFilter(event.target.value as PriorityFilter)
                }
              >
                <option value="all">All priorities</option>
                <option value="urgent">Urgent</option>
                <option value="high">High</option>
                <option value="normal">Normal</option>
              </select>
            </label>
            <label className={rosterClasses.filter}>
              <span>Status</span>
              <select
                className={rosterClasses.filterControl}
                aria-label="Filter investigations by status"
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
              >
                <option value="all">All statuses</option>
                {investigationStatuses.map((status) => (
                  <option key={status} value={status}>
                    {status.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className={rosterClasses.caption}>
            <span>Confirmed map locations</span>
            <span>{investigations.length}</span>
          </div>
          {loading && !issues ? (
            <div
              className="grid gap-2 px-3 py-4 text-xs text-openci-text-muted"
              role="status"
              aria-busy="true"
            >
              <span>Loading investigations and agent locations…</span>
              <i className="h-8 rounded bg-openci-surface-muted" />
              <i className="h-8 rounded bg-openci-surface-muted" />
              <i className="h-8 rounded bg-openci-surface-muted" />
            </div>
          ) : investigations.length ? (
            <ul className={rosterClasses.items}>
              {filteredInvestigations.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className={rosterClasses.item}
                    aria-pressed={
                      selection?.type === "investigation" &&
                      selection.id === item.id
                    }
                    onClick={() =>
                      onSelect({ type: "investigation", id: item.id })
                    }
                  >
                    <span
                      className={`priority-mark priority-${item.priority} mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${item.priority === "urgent" ? "bg-openci-danger" : item.priority === "high" ? "bg-openci-warning" : "bg-openci-border-strong"}`}
                      aria-hidden="true"
                    />
                    <span className={rosterClasses.itemMain}>
                      <span className={rosterClasses.itemTopline}>
                        <strong className={rosterClasses.itemTitle}>
                          {item.reference_number}
                        </strong>
                        <span
                          className={`priority-label priority-${item.priority} ${rosterClasses.priorityBadge}`}
                        >
                          {item.priority}
                        </span>
                      </span>
                      <span className={rosterClasses.address}>
                        {item.address_display}
                      </span>
                      <span className={rosterClasses.metadata}>
                        <span>
                          {item.agent_name
                            ? `${item.assignment_source === "manual" ? "Manual override" : "Automatically assigned"} · ${item.agent_name}`
                            : planningStatusLabel(
                                item.planning_status ?? "pending",
                              )}
                        </span>
                        {item.estimated_service_start_at && (
                          <span>
                            Service starts ·{" "}
                            {time(item.estimated_service_start_at)}
                          </span>
                        )}
                        {!item.estimated_service_start_at &&
                          item.estimated_arrival_at && (
                            <span>
                              Earliest arrival estimate (depart as soon as
                              possible) · {time(item.estimated_arrival_at)}
                            </span>
                          )}
                        <span>{item.status.replaceAll("_", " ")}</span>
                      </span>
                      {item.planning_reason && (
                        <span className="rounded bg-openci-warning-surface px-2 py-1 text-[11px] text-openci-warning">
                          {planningReasonCopy(item.planning_reason)}
                        </span>
                      )}
                      <span className="inline-flex items-center gap-1 text-[11px] text-openci-success">
                        <MapPin size={13} aria-hidden="true" /> Location
                        confirmed
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No mapped investigations">
              There are no investigation records with confirmed locations in
              this date and region.
            </EmptyState>
          )}
          {investigations.length > 0 && filteredInvestigations.length === 0 && (
            <p className={rosterClasses.emptyFilter}>
              No investigations match the current search and filters.
            </p>
          )}
        </section>
      )}

      {tab === "agents" && (
        <section className={rosterClasses.section} aria-label="Agents">
          <div className={rosterClasses.caption}>
            <span>Selected-date shifts</span>
            <span>{issues?.agents.length ?? agents.length}</span>
          </div>
          {issues?.agents.length ? (
            <ul className={rosterClasses.items}>
              {filteredAgents.map((agent) => {
                const routeAgent = routeAgentById.get(agent.id);
                const mapAgent = mappedAgentById.get(agent.id);
                const mapped = mappedAgentIds.has(agent.id);
                const assignedCount = investigations.filter(
                  (item) => item.agent_id === agent.id,
                ).length;
                const availability = !agent.is_active
                  ? "Inactive"
                  : agent.is_available === null
                    ? "No shift for this date"
                    : agent.is_available
                      ? "Available"
                      : "Unavailable";
                return (
                  <li key={agent.id}>
                    <button
                      type="button"
                      className={`${rosterClasses.item} agent-roster-item`}
                      aria-pressed={
                        selection?.type === "agent" && selection.id === agent.id
                      }
                      onClick={() => onSelect({ type: "agent", id: agent.id })}
                    >
                      <span
                        className={`agent-roster-symbol ${rosterClasses.icon} ${mapped ? "has-location border-openci-info-border bg-openci-info-surface text-openci-info" : "no-location border-openci-warning-border bg-openci-warning-surface text-openci-warning"}`}
                        aria-hidden="true"
                      >
                        {mapped ? <Users size={16} /> : <MapPinOff size={16} />}
                      </span>
                      <span className={rosterClasses.itemMain}>
                        <span className={rosterClasses.itemTopline}>
                          <strong className="min-w-0 break-words text-xs font-semibold text-openci-text">
                            {agent.name}
                          </strong>
                          <span
                            className={`availability-label shrink-0 rounded-full border px-1.5 py-0.5 text-[10px] ${agent.is_available ? "available border-openci-success-border bg-openci-success-surface text-openci-success" : "unavailable border-openci-warning-border bg-openci-warning-surface text-openci-warning"}`}
                          >
                            {availability}
                          </span>
                        </span>
                        <span className={rosterClasses.address}>
                          {mapAgent?.region_label ??
                            agent.region_code ??
                            "Region not set"}
                          {agent.shift_starts_at && agent.shift_ends_at
                            ? ` · ${time(agent.shift_starts_at)}–${time(agent.shift_ends_at)}`
                            : ""}
                        </span>
                        <span className={rosterClasses.metadata}>
                          <span>
                            {assignedCount} assigned{" "}
                            {assignedCount === 1
                              ? "investigation"
                              : "investigations"}
                          </span>
                          <span>
                            {routeStatusLabel(
                              routeAgent?.route_status ?? "none",
                            )}
                          </span>
                          <span>
                            {mapped
                              ? (mapAgent?.start.label ??
                                "Starting point on map")
                              : "Starting point missing"}
                          </span>
                        </span>
                        {routeAgent && (
                          <span className={rosterClasses.metadata}>
                            <span>{routeAgent.open_case_count} open cases</span>
                            <span>
                              {routeAgent.remaining_open_capacity ?? "—"}{" "}
                              remaining capacity
                            </span>
                            <span>
                              Shift limit {routeAgent.shift?.max_visits ?? "—"}{" "}
                              visits
                            </span>
                            {routeAgent.planning_status !== "idle" && (
                              <span>
                                {routeAgent.planning_status === "queued"
                                  ? "Planning queued"
                                  : routeAgent.planning_status === "running"
                                    ? "Optimizing routes"
                                    : "Planning failed"}
                              </span>
                            )}
                          </span>
                        )}
                        {routeAgent?.route && (
                          <span className={rosterClasses.metadata}>
                            <span>
                              Road travel ·{" "}
                              {duration(routeAgent.route.total_travel_seconds)}
                            </span>
                            <span>
                              Visit time ·{" "}
                              {duration(
                                routeAgent.stops.reduce(
                                  (total, stop) =>
                                    total + stop.service_duration_seconds,
                                  0,
                                ),
                              )}
                            </span>
                            <span>
                              Sequence ·{" "}
                              {routeAgent.stops
                                .map((stop) => stop.reference_number)
                                .join(" → ") || "No stops"}
                            </span>
                          </span>
                        )}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : (
            <EmptyState title="No agent shifts for this scope">
              Choose another date or clear the optional region filter.
            </EmptyState>
          )}
          {issues?.agents.length && !filteredAgents.length ? (
            <p className={rosterClasses.emptyFilter}>
              No agents match “{query}”.
            </p>
          ) : null}
          {issues?.unlocated_agents.length ? (
            <div className={rosterClasses.manageShifts}>
              <p className="mb-0!">
                {issues.unlocated_agents.length} agent starting point
                {issues.unlocated_agents.length === 1 ? "" : "s"} not available
                on the map.
              </p>
              <Link
                className="font-medium text-openci-accent-strong"
                to={`/field-agents?date=${date}`}
              >
                Manage shifts
              </Link>
            </div>
          ) : null}
        </section>
      )}

      {tab === "confirmation" && (
        <section
          className={rosterClasses.section}
          aria-label="Needs confirmation"
        >
          {unlocatedInvestigations.length === 0 &&
          unlocatedAgents.length === 0 ? (
            <EmptyState title="Locations are ready">
              All investigation locations in this scope are confirmed and agent
              starting points are available.
            </EmptyState>
          ) : (
            <>
              {unlocatedInvestigations.length > 0 && (
                <>
                  <div className={rosterClasses.caption}>
                    <span>Investigation locations</span>
                    <span>{unlocatedInvestigations.length}</span>
                  </div>
                  <ul className={`${rosterClasses.items} confirmation-items`}>
                    {unlocatedInvestigations
                      .filter((item) =>
                        matches(
                          query,
                          item.reference_number,
                          item.status,
                          item.region_code,
                        ),
                      )
                      .map((item) => (
                        <li key={item.id}>
                          <Link
                            className={`${rosterClasses.item} confirmation-link`}
                            to={`/investigations/${item.id}#location`}
                          >
                            <span
                              className={`agent-roster-symbol no-location ${rosterClasses.icon} border-openci-warning-border bg-openci-warning-surface text-openci-warning`}
                              aria-hidden="true"
                            >
                              <MapPinOff size={16} />
                            </span>
                            <span className={rosterClasses.itemMain}>
                              <span
                                className={rosterClasses.confirmationTopline}
                              >
                                <strong className={rosterClasses.itemTitle}>
                                  {item.reference_number}
                                </strong>
                                <span className="shrink-0 rounded-full border border-openci-warning-border bg-openci-warning-surface px-1.5 py-0.5 text-[10px] text-openci-warning">
                                  Needs confirmation
                                </span>
                              </span>
                              <span className={rosterClasses.address}>
                                {item.status.replaceAll("_", " ")} ·{" "}
                                {item.region_code ?? "Region not set"}
                              </span>
                              <span className="text-[11px] leading-snug text-openci-text-muted">
                                Not shown on map until a location is confirmed
                              </span>
                            </span>
                          </Link>
                        </li>
                      ))}
                  </ul>
                </>
              )}
              {unlocatedAgents.length > 0 && (
                <div
                  className={`${rosterClasses.manageShifts} confirmation-shifts`}
                >
                  <div className="flex items-center justify-between gap-2 text-xs text-openci-text-muted">
                    <span>Agent starting points</span>
                    <span>{unlocatedAgents.length}</span>
                  </div>
                  <p className="mb-0!">
                    These agents have no dated starting point to place on the
                    map.
                  </p>
                  <Link
                    className="font-medium text-openci-accent-strong"
                    to={`/field-agents?date=${date}`}
                  >
                    Manage shifts
                  </Link>
                </div>
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}
