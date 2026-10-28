import { useCallback } from "react";
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
  return (
    <>
      <PageHeader
        title="My Route"
        description="Your current investigation route. Routes refresh automatically after assignments. Starting points are manually configured."
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
        {resource.loading ? (
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
