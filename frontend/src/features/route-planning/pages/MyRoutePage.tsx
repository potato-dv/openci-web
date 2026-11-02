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
  const { token, user } = useSession();
  const [params, setParams] = useSearchParams();
  const date = params.get("date") ?? manilaToday();
  const resource = useResource(
    useCallback((signal) => getAgentRoute(token, date, signal), [token, date]),
  );
  const routeRefreshPending =
    resource.data?.reason === "route_refresh_pending";
  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === "visible") resource.refresh();
    };
    const timer = window.setInterval(
      refresh,
      routeRefreshPending ? 4000 : 10000,
    );
    return () => window.clearInterval(timer);
  }, [resource.refresh, routeRefreshPending]);
  return (
    <>
      <PageHeader
        title="My Route"
        description="Your remaining route starts from your latest reported visit when available, then falls back to your configured shift location. Reported locations are estimates, not live GPS."
        actions={
          <>
            <label>
              Work date
              <input
                type="date"
                value={date}
                onChange={(event) => setParams({ date: event.target.value })}
              />
            </label>
            <Button onClick={resource.refresh}>Refresh</Button>
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
            />
          )
        )}
      </section>
    </>
  );
}
