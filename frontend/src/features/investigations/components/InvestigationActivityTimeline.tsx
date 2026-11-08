import { useCallback, useEffect } from "react";
import { getInvestigationActivity } from "@/features/reports/api";
import { useResource } from "@/hooks/useResource";
import { WorkspacePanel } from "@/components/layout/WorkspacePanel";
import { InlineAlert, Skeleton } from "@/components/ui/Primitives";

export function InvestigationActivityTimeline({
  token,
  investigationId,
  refreshKey,
}: {
  token: string;
  investigationId: number;
  refreshKey: number;
}) {
  const resource = useResource(
    useCallback(
      (signal) => getInvestigationActivity(token, investigationId, signal),
      [investigationId, token],
    ),
    {
      refetchOnFocus: true,
      refetchOnReconnect: true,
      staleTimeMs: 30_000,
    },
  );
  const refresh = resource.refresh;
  useEffect(() => {
    if (refreshKey > 0) refresh();
  }, [refreshKey, refresh]);

  const items = resource.data?.items ?? [];

  return (
    <WorkspacePanel
      title="Investigation activity"
      description="A record of work on this investigation. This timeline does not show live location."
      aria-label="Investigation activity"
    >
      {resource.error && (
        <InlineAlert onRetry={resource.refresh}>{resource.error}</InlineAlert>
      )}
      {resource.loading && !resource.data ? (
        <Skeleton rows={3} />
      ) : items.length === 0 ? (
        resource.error ? null : (
          <p className="mt-1.5 mb-3.5 text-[13px] text-openci-text-muted">
            No activity recorded.
          </p>
        )
      ) : (
        <ol className="m-0 grid list-none gap-0 border-l border-[#cbd8eb] p-0 pl-5">
          {items.map((item) => (
            <li
              className="relative grid gap-1 border-b border-[#e9eef5] py-4 first:pt-0 last:border-b-0 last:pb-0 before:absolute before:-left-[25px] before:top-5 before:size-2 before:rounded-full before:bg-[#3261c5] first:before:top-1"
              key={item.id}
            >
              <div className="flex flex-wrap justify-between gap-4">
                <strong className="text-[13px] font-semibold text-[#253b5d]">{item.label}</strong>
                <time
                  className="text-[13px] text-openci-text-muted"
                  dateTime={item.created_at}
                >
                  {new Intl.DateTimeFormat("en-PH", {
                    dateStyle: "medium",
                    timeStyle: "short",
                    timeZone: "Asia/Manila",
                  }).format(new Date(item.created_at))}
                </time>
              </div>
              {item.actor_name && (
                <span className="text-[13px] text-openci-text-muted">
                  {item.actor_name}
                </span>
              )}
            </li>
          ))}
        </ol>
      )}
    </WorkspacePanel>
  );
}
