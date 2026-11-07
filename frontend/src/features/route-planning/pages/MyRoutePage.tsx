import { useCallback, useEffect } from "react";
import { useSearchParams } from "react-router";
import { useSession } from "@/app/session";
import { getAgentRoute } from "@/features/route-planning/api";
import { useResource } from "@/hooks/useResource";
import { PageHeader } from "@/components/layout/PageHeader";
import { AgentRouteView } from "@/features/agents/components/AgentRouteView";
import { Button, InlineAlert, Skeleton } from "@/components/ui/Primitives";
import { manilaToday } from "@/utils/format";
export function MyRoutePage() {
  const { token, user, agentPermissions } = useSession();
  const [params, setParams] = useSearchParams();
  const canViewHistory = agentPermissions?.["route.view_own_history"] ?? true;
  const today = manilaToday();
  const date = canViewHistory ? params.get("date") ?? today : today;
  const resource = useResource(
    useCallback((signal) => getAgentRoute(token, date, signal), [token, date]),
  );
  const refreshRoute = resource.refresh;
  const routeRefreshPending =
    resource.data?.reason === "route_refresh_pending";
  useEffect(() => {
    if (!canViewHistory && params.has("date")) setParams({}, { replace: true });
  }, [canViewHistory, params, setParams]);
  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === "visible") refreshRoute();
    };
    const timer = window.setInterval(
      refresh,
      routeRefreshPending ? 4000 : 10000,
    );
    return () => window.clearInterval(timer);
  }, [refreshRoute, routeRefreshPending]);
  return (
    <>
      <PageHeader
        title="My Route"
        description="Your route uses the latest reported visit when available, then your shift starting point. Reported locations are estimates, not live GPS."
        actions={
          <>
            {canViewHistory && <label>
              Work date
              <input
                type="date"
                value={date}
                onChange={(event) => setParams({ date: event.target.value })}
              />
            </label>}
            <Button onClick={refreshRoute}>Refresh</Button>
          </>
        }
      />
      <section className="content-card">
        {resource.loading && !resource.data ? (
          <Skeleton rows={6} />
        ) : resource.error ? (
          <InlineAlert onRetry={resource.refresh}>{resource.error}</InlineAlert>
        ) : (
          resource.data && (
            <AgentRouteView
              data={resource.data}
              agentId={user.id}
              agentName={user.name}
              token={token}
              canAct
              onRefresh={resource.refresh}
            />
          )
        )}
      </section>
    </>
  );
}
