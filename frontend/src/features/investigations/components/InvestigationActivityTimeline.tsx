import { useEffect, useState } from "react";
import { getInvestigationActivity } from "@/features/reports/api";
import type { InvestigationActivityItem } from "@/types/api";

export function InvestigationActivityTimeline({
  token,
  investigationId,
}: {
  token: string;
  investigationId: number;
}) {
  const requestKey = `${investigationId}:${token}`;
  const [result, setResult] = useState<{
    key: string;
    items: InvestigationActivityItem[];
    error: string;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    void getInvestigationActivity(token, investigationId)
      .then((response) => {
        if (!cancelled)
          setResult({ key: requestKey, items: response.items, error: "" });
      })
      .catch((loadError: unknown) => {
        if (!cancelled)
          setResult({
            key: requestKey,
            items: [],
            error:
              loadError instanceof Error
                ? loadError.message
                : "Could not load activity.",
          });
      });
    return () => {
      cancelled = true;
    };
  }, [investigationId, requestKey, token]);

  const current = result?.key === requestKey ? result : null;
  const loading = current === null;
  const items = current?.items ?? [];
  const error = current?.error ?? "";

  return (
    <section
      className="content-card"
      aria-labelledby="investigation-activity-heading"
    >
      <h3 className="m-0" id="investigation-activity-heading">
        Investigation activity
      </h3>
      <p className="mt-1.5 mb-3.5 text-[13px] text-openci-text-muted">
        A record of the work on this investigation. This timeline does not show
        live location.
      </p>
      {loading ? (
        <p
          className="mt-1.5 mb-3.5 text-[13px] text-openci-text-muted"
          role="status"
        >
          Loading activity…
        </p>
      ) : error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : items.length === 0 ? (
        <p className="mt-1.5 mb-3.5 text-[13px] text-openci-text-muted">
          No activity recorded.
        </p>
      ) : (
        <ol className="mt-3.5 mb-3.5 grid list-none gap-3 p-0">
          {items.map((item) => (
            <li
              className="grid gap-1 border-t border-openci-border pt-3"
              key={item.id}
            >
              <div className="flex flex-wrap justify-between gap-4">
                <strong>{item.label}</strong>
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
    </section>
  );
}
