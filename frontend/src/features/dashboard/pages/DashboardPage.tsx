import { useCallback } from "react";
import { Link } from "react-router";
import {
  ArrowUpRight,
  Search,
  CircleDot,
  UserRoundCheck,
  FileCheck2,
  MapPinned,
  Activity,
  Route,
} from "lucide-react";
import { useSession } from "@/app/session";
import { getAgentRoute } from "@/features/route-planning/api";
import { getInvestigations } from "@/features/investigations/api";
import { getReportQueue } from "@/features/reports/api";
import { useResource } from "@/hooks/useResource";
import { PageHeader } from "@/components/layout/PageHeader";
import { WorkspaceMetric } from "@/components/layout/WorkspaceMetric";
import { WorkspacePanel } from "@/components/layout/WorkspacePanel";
import { ResourceFreshness } from "@/components/data/ResourceFreshness";
import { InvestigationTable } from "@/components/data/InvestigationTable";
import {
  EmptyState,
  InlineAlert,
  Skeleton,
} from "@/components/ui/Primitives";
import { manilaToday, time } from "@/utils/format";
import { PLANNING_ENABLED } from "@/config";
export function DashboardPage() {
  const { token, user } = useSession();
  const data = useResource(
    useCallback(
      (signal) =>
        getInvestigations(
          token,
          new URLSearchParams({ page_size: "5" }),
          signal,
        ),
      [token],
    ),
    {
      resourceKeys: ["investigations.list", "dashboard.investigations"],
      refetchOnFocus: true,
      refetchOnReconnect: true,
      staleTimeMs: 30_000,
    },
  );
  const queue = useResource(
    useCallback(
      async (signal) =>
        user.role !== "agent"
          ? getReportQueue(
              token,
              new URLSearchParams({ page_size: "5" }),
              signal,
            )
          : null,
      [token, user.role],
    ),
    {
      resourceKeys: user.role === "agent" ? ["dashboard.reports"] : ["reports.queue", "dashboard.reports"],
      refetchOnFocus: true,
      refetchOnReconnect: true,
      staleTimeMs: 30_000,
    },
  );
  const route = useResource(
    useCallback(
      async (signal) =>
        user.role === "agent" && PLANNING_ENABLED
          ? getAgentRoute(token, manilaToday(), signal)
          : null,
      [token, user.role],
    ),
    {
      resourceKeys: user.role === "agent" ? ["route.own", "dashboard.route"] : ["dashboard.route"],
      refetchOnFocus: true,
      refetchOnReconnect: true,
      staleTimeMs: 30_000,
    },
  );
  const corrections = useResource(
    useCallback(
      async (signal) =>
        user.role === "agent"
          ? getInvestigations(
              token,
              new URLSearchParams({
                status: "returned_for_correction",
                page_size: "5",
                sort: "created_at",
                direction: "asc",
              }),
              signal,
            )
          : null,
      [token, user.role],
    ),
    {
      resourceKeys: ["investigations.list", "dashboard.investigations"],
      refetchOnFocus: true,
      refetchOnReconnect: true,
      staleTimeMs: 30_000,
    },
  );
  const facets = data.data?.facets;
  const manage = user.role !== "agent";
  const metrics = manage
    ? [
        {
          label: "Total investigations",
          value: data.data
            ? Object.values(data.data.facets.status).reduce((a, b) => a + b, 0)
            : undefined,
          icon: Search,
          to: "/investigations",
        },
        {
          label: "Pending",
          value: facets?.status.pending,
          icon: CircleDot,
          to: "/investigations?status=pending",
        },
        {
          label: "Assigned",
          value: facets?.status.assigned,
          icon: UserRoundCheck,
          to: "/investigations?status=assigned",
        },
        {
          label: "Under review",
          value: facets?.status.under_review,
          icon: FileCheck2,
          to: "/reports",
        },
        {
          label: "Unconfirmed locations",
          value: facets?.location_unconfirmed,
          icon: MapPinned,
          to: "/investigations?location_confirmed=false",
        },
      ]
    : [
        {
          label: "Assigned to you",
          value: facets?.status.assigned,
          icon: Search,
          to: "/investigations?status=assigned",
        },
        {
          label: "In progress",
          value: facets?.status.in_progress,
          icon: Activity,
          to: "/investigations?status=in_progress",
        },
        {
          label: "Needs correction",
          value: facets?.status.returned_for_correction,
          icon: FileCheck2,
          to: "/investigations?status=returned_for_correction",
        },
        ...(PLANNING_ENABLED
          ? [
              {
                label: "Today's route stops",
                value: route.data?.stops.length,
                icon: Route,
                to: "/my-route",
              },
            ]
          : []),
      ];
  const workflow = manage && facets ? [
    { label: "Pending", count: facets.status.pending, color: "bg-[#9aa7bb]" },
    { label: "Assigned", count: facets.status.assigned, color: "bg-[#3c6bd1]" },
    { label: "In progress", count: facets.status.in_progress, color: "bg-[#5d91ea]" },
    { label: "Under review", count: facets.status.under_review, color: "bg-[#8b68cb]" },
    { label: "Needs correction", count: facets.status.returned_for_correction, color: "bg-[#d99b45]" },
    { label: "Completed", count: facets.status.completed, color: "bg-[#31a276]" },
    { label: "Cancelled", count: facets.status.cancelled, color: "bg-[#c3ccd8]" },
  ] : [];
  const workflowTotal = workflow.reduce((total, item) => total + item.count, 0);
  const dashboardResources = manage
    ? [data, queue]
    : [data, route, corrections];
  const dashboardLastUpdatedAt = dashboardResources.every(
    (resource) => resource.lastUpdatedAt !== null,
  )
    ? Math.min(...dashboardResources.map((resource) => resource.lastUpdatedAt!))
    : null;
  const dashboardRefreshing = dashboardResources.some((resource) => resource.refreshing);
  const panelLinkClass = "inline-flex items-center gap-1 text-xs font-semibold text-[#315cb0] no-underline hover:underline";
  const listClass = "divide-y divide-[#e9eef5]";
  const rowClass = "group flex min-w-0 items-center justify-between gap-4 py-3.5 text-[#253b5c] no-underline first:pt-0 last:pb-0";
  return (
    <>
      <PageHeader
        title="Dashboard"
        actions={
          <ResourceFreshness
            loading={dashboardRefreshing}
            lastUpdatedAt={dashboardLastUpdatedAt}
          />
        }
      />
      {data.error && <InlineAlert onRetry={data.refresh}>{data.error}</InlineAlert>}
      {data.loading && !data.data ? <Skeleton rows={2} /> : data.data ? (
        <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4" role="group" aria-label="Workload summary">
          {(manage ? metrics.slice(0, 4) : metrics).map((metric) => <WorkspaceMetric key={metric.label} {...metric} />)}
        </div>
      ) : null}
      {manage && (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(320px,1fr)]">
          <WorkspacePanel title="Investigation workflow" description="Current status across all investigations">
            {workflowTotal > 0 ? (
              <>
                <div className="flex h-3 overflow-hidden rounded-full bg-[#edf2f8]" role="img" aria-label={workflow.map((item) => `${item.label}: ${item.count}`).join(", ")}>
                  {workflow.filter((item) => item.count > 0).map((item) => <span key={item.label} className={item.color} style={{ width: `${(item.count / workflowTotal) * 100}%` }} />)}
                </div>
                <ul className="mt-5 grid grid-cols-2 gap-x-5 gap-y-3 text-xs sm:grid-cols-3">
                  {workflow.map((item) => <li key={item.label} className="flex items-center gap-2"><span className={`size-2 rounded-full ${item.color}`} /><span className="min-w-0 flex-1 text-[#64758e]">{item.label}</span><strong className="tabular-nums text-[#243a5b]">{item.count}</strong></li>)}
                </ul>
              </>
            ) : <EmptyState title="No workflow data yet">Investigation status will appear here.</EmptyState>}
            <Link to="/investigations?location_confirmed=false" className="mt-6 flex items-center justify-between gap-3 rounded-lg border border-[#d8e4f5] bg-[#f3f7fd] px-4 py-3 text-[12px] no-underline">
              <span className="font-medium text-[#31527d]">Locations awaiting confirmation</span><strong className="text-base tabular-nums text-[#244b9d]">{facets?.location_unconfirmed ?? "—"}</strong>
            </Link>
          </WorkspacePanel>
          <WorkspacePanel title="Reports awaiting review" action={<Link className={panelLinkClass} to="/reports">Open queue <ArrowUpRight size={14} /></Link>}>
            {queue.loading && !queue.data ? <Skeleton rows={3} /> : queue.error && !queue.data ? <InlineAlert onRetry={queue.refresh}>{queue.error}</InlineAlert> : queue.data?.items.length ? (
              <ul className={listClass}>{queue.data.items.map((item) => <li key={item.report_id}><Link className={rowClass} to={`/investigations/${item.investigation_id}#report`}><span className="min-w-0"><strong className="block truncate text-[13px]">{item.subject_name}</strong><span className="mt-1 block text-[11px] text-[#6e7e95]">{item.reference_number} · {item.author_name} · Version {item.version}</span></span><ArrowUpRight className="shrink-0 text-[#7c8daa] group-hover:text-[#315cb0]" size={16} /></Link></li>)}</ul>
            ) : <EmptyState title="No reports awaiting review">Submitted reports will appear here.</EmptyState>}
          </WorkspacePanel>
        </div>
      )}
      {!manage && (
        <div className="grid gap-5 lg:grid-cols-2">
          {PLANNING_ENABLED && <WorkspacePanel title="Today's route stops" action={<Link className={panelLinkClass} to="/my-route">View My Route <ArrowUpRight size={14} /></Link>}>
            {route.loading && !route.data ? <Skeleton rows={3} /> : route.error && !route.data ? <InlineAlert onRetry={route.refresh}>{route.error}</InlineAlert> : route.data?.stops.length ? (
              <ol className={listClass}>{route.data.stops.slice(0, 5).map((stop) => <li key={stop.investigation_id}><Link className={rowClass} to={`/investigations/${stop.investigation_id}`}><span className="min-w-0"><strong className="block truncate text-[13px]">{stop.sequence}. {stop.reference_number}</strong><span className="mt-1 block truncate text-[11px] text-[#6e7e95]">{stop.address_display}</span></span><span className="shrink-0 text-[11px] text-[#60738f]">{stop.planned_arrival_at ? time(stop.planned_arrival_at) : "Time unavailable"}</span></Link></li>)}</ol>
            ) : <EmptyState title="No route stops for today">Your route will appear after your supervisor assigns an investigation. Stop order is generated automatically.</EmptyState>}
          </WorkspacePanel>}
          <WorkspacePanel title="Reports needing correction" action={<Link className={panelLinkClass} to="/investigations?status=returned_for_correction">View all <ArrowUpRight size={14} /></Link>}>
            {corrections.loading && !corrections.data ? <Skeleton rows={3} /> : corrections.error && !corrections.data ? <InlineAlert onRetry={corrections.refresh}>{corrections.error}</InlineAlert> : corrections.data?.items.length ? (
              <ul className={listClass}>{corrections.data.items.map((item) => <li key={item.id}><Link className={rowClass} to={`/investigations/${item.id}#report`}><span className="min-w-0"><strong className="block truncate text-[13px]">{item.subject_name}</strong><span className="mt-1 block text-[11px] text-[#6e7e95]">{item.reference_number} · Update and resubmit report</span></span><ArrowUpRight className="shrink-0 text-[#7c8daa]" size={16} /></Link></li>)}</ul>
            ) : <EmptyState title="No reports need correction">Reports returned by your supervisor will appear here.</EmptyState>}
          </WorkspacePanel>
        </div>
      )}
      <WorkspacePanel title="Recent investigations" action={<Link className={panelLinkClass} to="/investigations">View all <ArrowUpRight size={14} /></Link>} bodyClassName="p-4 md:p-5">
        {data.loading && !data.data ? <Skeleton /> : data.data?.items.length ? <InvestigationTable items={data.data.items} /> : data.data ? <EmptyState title="No investigations yet">Your recent investigation records will appear here.</EmptyState> : null}
      </WorkspacePanel>
    </>
  );
}
