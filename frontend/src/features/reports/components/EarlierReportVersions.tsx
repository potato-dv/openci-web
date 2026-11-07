import type { Report } from "@/types/api";

type EarlierReportVersionsProps = {
  versions: Report[];
  currentReportId: number | undefined;
  formatVisitDate: (value: string | null) => string;
};

export function EarlierReportVersions({
  versions,
  currentReportId,
  formatVisitDate,
}: EarlierReportVersionsProps) {
  const earlierVersions = versions.filter(
    (item) => item.id !== currentReportId,
  );
  if (earlierVersions.length === 0) return null;

  return (
    <details className="report-version-history">
      <summary>Earlier report versions</summary>
      <div className="report-version-list grid gap-1.5">
        {earlierVersions.map((item) => (
          <article className="report-version-item rounded-md border border-openci-border px-2.5 py-2" key={item.id}>
            <h4 className="mb-1 text-[13px] font-semibold text-openci-text">
              Version {item.version} · {item.status.replaceAll("_", " ")}
            </h4>
            <p className="workflow-meta mb-2">
              {item.visited_at
                ? `Visit recorded ${formatVisitDate(item.visited_at).replace("T", " ")}`
                : "No visit time recorded"}
            </p>
            <p className="mb-0 whitespace-pre-wrap break-words text-[13px] leading-relaxed text-openci-text-muted">{item.content}</p>
          </article>
        ))}
      </div>
    </details>
  );
}
