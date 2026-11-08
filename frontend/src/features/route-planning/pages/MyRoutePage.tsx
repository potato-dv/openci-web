import { useCallback, useEffect } from "react";
import { useSearchParams } from "react-router";
import { useSession } from "@/app/session";
import { getAgentRoute } from "@/features/route-planning/api";
import { useResource } from "@/hooks/useResource";
import { PageHeader } from "@/components/layout/PageHeader";
import { ResourceFreshness } from "@/components/data/ResourceFreshness";
import { WorkspacePanel } from "@/components/layout/WorkspacePanel";
import { AgentRouteView } from "@/features/agents/components/AgentRouteView";
import { InlineAlert, Skeleton } from "@/components/ui/Primitives";
import { manilaToday } from "@/utils/format";
export function MyRoutePage() {
  const { token, user, agentPermissions } = useSession();
  const [params, setParams] = useSearchParams();
  const canViewHistory = agentPermissions?.["route.view_own_history"] ?? true;
  const today = manilaToday();
  const date = canViewHistory ? params.get("date") ?? today : today;
  const resource = useResource(
    useCallback((signal) => getAgentRoute(token, date, signal), [token, date]),
    {
      refetchOnFocus: true,
      refetchOnReconnect: true,
      staleTimeMs: 15_000,
      refetchInterval: (data) => {
        if (date !== today) return false;
        if (!data) return 10_000;
        if (data.reason === "route_refresh_pending") return 4_000;
        return false;
      },
    },
  );
  useEffect(() => {
    if (!canViewHistory && params.has("date")) setParams({}, { replace: true });
  }, [canViewHistory, params, setParams]);
  return (
    <>
      <PageHeader
        title="My Route"
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
            <ResourceFreshness
              loading={resource.refreshing}
              lastUpdatedAt={resource.lastUpdatedAt}
            />
          </>
        }
      />
      <WorkspacePanel title="Published route" description="Ordered visits and route information for the selected work date." bodyClassName="p-4 md:p-5">
        {resource.loading && !resource.data ? (
          <Skeleton rows={6} />
        ) : resource.error && !resource.data ? (
          <InlineAlert onRetry={resource.refresh}>{resource.error}</InlineAlert>
        ) : (
          resource.data && (
            <>
            {resource.error && <InlineAlert onRetry={resource.refresh}>{resource.error}</InlineAlert>}
            <AgentRouteView
              data={resource.data}
              agentId={user.id}
              agentName={user.name}
              token={token}
              canAct
              onRefresh={resource.refresh}
            />
            </>
          )
        )}
      </WorkspacePanel>
    </>
  );
}
