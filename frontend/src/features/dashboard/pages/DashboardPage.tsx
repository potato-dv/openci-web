import { useCallback } from "react";
import { Link } from "react-router";
import { RefreshCw, ArrowUpRight } from "lucide-react";
import { useSession } from "@/app/session";
import { getAgentRoute } from "@/features/route-planning/api";
import { getInvestigations } from "@/features/investigations/api";
import { getReportQueue } from "@/features/reports/api";
import { useResource } from "@/hooks/useResource";
import { PageHeader } from "@/components/layout/PageHeader";
import { InvestigationTable } from "@/components/data/InvestigationTable";
import {
  Button,
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
  );
  const route = useResource(
    useCallback(
      async (signal) =>
        user.role === "agent" && PLANNING_ENABLED
          ? getAgentRoute(token, manilaToday(), signal)
          : null,
      [token, user.role],
    ),
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
  );
  const facets = data.data?.facets;
  const manage = user.role !== "agent";
  const metrics = manage
    ? [
        {
          label: "Total investigations",
          value: data.data
            ? Object.values(data.data.facets.status).reduce((a, b) => a + b, 0)
            : 0,
          to: "/investigations",
        },
        {
          label: "Pending",
          value: facets?.status.pending,
          to: "/investigations?status=pending",
        },
        {
          label: "Assigned",
          value: facets?.status.assigned,
          to: "/investigations?status=assigned",
        },
        {
          label: "Under review",
          value: facets?.status.under_review,
          to: "/reports",
        },
        {
          label: "Unconfirmed locations",
          value: facets?.location_unconfirmed,
          to: "/investigations?location_confirmed=false",
        },
      ]
    : [
        {
          label: "Assigned to you",
          value: facets?.status.assigned,
          to: "/investigations?status=assigned",
        },
        {
          label: "In progress",
          value: facets?.status.in_progress,
          to: "/investigations?status=in_progress",
        },
        {
          label: "Needs correction",
          value: facets?.status.returned_for_correction,
          to: "/investigations?status=returned_for_correction",
        },
        ...(PLANNING_ENABLED
          ? [
              {
                label: "Today's route stops",
                value: route.data?.stops.length ?? 0,
                to: "/my-route",
              },
            ]
          : []),
      ];
  return (
    <>
      <PageHeader
        title="Dashboard"
        description={
          manage
            ? "An overview of your investigation workload and next actions."
            : "Your assigned work and today's route stops."
        }
        actions={
          <Button
            onClick={() => {
              data.refresh();
              if (manage) queue.refresh();
              else {
                route.refresh();
                corrections.refresh();
              }
            }}
            disabled={data.loading}
          >
            <RefreshCw size={16} aria-hidden="true" />
            Refresh
          </Button>
        }
      />
      {data.error && (
        <InlineAlert onRetry={data.refresh}>{data.error}</InlineAlert>
      )}
      {data.loading ? (
        <Skeleton rows={2} />
      ) : (
        <div className="metrics-strip">
          {metrics.map((metric) => (
            <Link key={metric.label} to={metric.to}>
              <span>{metric.label}</span>
              <strong>{metric.value ?? 0}</strong>
              <ArrowUpRight size={14} aria-hidden="true" />
            </Link>
          ))}
        </div>
      )}
      <section className="content-card">
        <div className="section-title">
          <h2>Recent investigations</h2>
          <Link to="/investigations">View all</Link>
        </div>
        {data.loading ? (
          <Skeleton />
        ) : data.data?.items.length ? (
          <InvestigationTable items={data.data.items} />
        ) : (
          <EmptyState title="No investigations yet">
            Your recent investigation records will appear here.
          </EmptyState>
        )}
      </section>
      {(manage || PLANNING_ENABLED) && (
        <section className="content-card dashboard-queue">
          <div className="section-title">
            <h2>
              {manage ? "Reports awaiting review" : "Today's route stops"}
            </h2>
            <Link to={manage ? "/reports" : "/my-route"}>
              {manage ? "Open review queue" : "View My Route"}
            </Link>
          </div>
          {manage ? (
            queue.loading ? (
              <Skeleton rows={3} />
            ) : queue.error ? (
              <InlineAlert onRetry={queue.refresh}>{queue.error}</InlineAlert>
            ) : queue.data?.items.length ? (
              <ul className="work-list">
                {queue.data.items.map((item) => (
                  <li key={item.report_id}>
                    <Link
                      to={`/investigations/${item.investigation_id}#report`}
                    >
                      <strong>{item.reference_number}</strong>
                      <span>{item.subject_name}</span>
                      <small>
                        {item.author_name} · Version {item.version}
                      </small>
                      <ArrowUpRight aria-hidden="true" size={16} />
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="No reports awaiting review">
                Submitted reports will appear here.
              </EmptyState>
            )
          ) : route.loading ? (
            <Skeleton rows={3} />
          ) : route.error ? (
            <InlineAlert onRetry={route.refresh}>{route.error}</InlineAlert>
          ) : route.data?.stops.length ? (
            <ol className="work-list">
              {route.data.stops.slice(0, 5).map((stop) => (
                <li key={stop.investigation_id}>
                  <Link to={`/investigations/${stop.investigation_id}`}>
                    <strong>
                      {stop.sequence}. {stop.reference_number}
                    </strong>
                    <span>{stop.address_display}</span>
                    <small>
                      Estimated arrival {time(stop.estimated_arrival_at)}
                    </small>
                  </Link>
                </li>
              ))}
            </ol>
          ) : (
            <EmptyState title="No route stops for today">
              Your route will appear after your supervisor assigns an
              investigation. Stop order is generated automatically.
            </EmptyState>
          )}
        </section>
      )}
      {!manage && (
        <section className="content-card dashboard-queue">
          <div className="section-title">
            <h2>Reports needing correction</h2>
            <Link to="/investigations?status=returned_for_correction">
              View all
            </Link>
          </div>
          {corrections.loading ? (
            <Skeleton rows={3} />
          ) : corrections.error ? (
            <InlineAlert onRetry={corrections.refresh}>
              {corrections.error}
            </InlineAlert>
          ) : corrections.data?.items.length ? (
            <ul className="work-list">
              {corrections.data.items.map((item) => (
                <li key={item.id}>
                  <Link to={`/investigations/${item.id}#report`}>
                    <strong>{item.reference_number}</strong>
                    <span>{item.subject_name}</span>
                    <small>Update and resubmit report</small>
                    <ArrowUpRight size={16} aria-hidden="true" />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No reports need correction">
              Reports returned by your supervisor will appear here.
            </EmptyState>
          )}
        </section>
      )}
    </>
  );
}
