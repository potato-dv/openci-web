import type {
  AgentPermissionFeature,
  AgentPermissionHistoryItem,
} from "@/types/api";

type PermissionHistoryPanelProps = {
  history: AgentPermissionHistoryItem[];
  features: Omit<AgentPermissionFeature, "override" | "effective_allowed">[];
};

const legacyHistoryFeatures = [
  {
    code: "investigation.view_own_report_history",
    name: "View own report history",
  },
  {
    code: "investigation.view_own_activity",
    name: "View own investigation activity",
  },
  {
    code: "investigation.view_own_completed",
    name: "View own completed investigations",
  },
] as const;

function displayEffect(value: boolean) {
  return value ? "Allowed" : "Denied";
}

function displayOverride(value: string | undefined) {
  if (value === "allow") return "Allow";
  if (value === "deny") return "Deny";
  return "Use default";
}

function changesFor(
  item: AgentPermissionHistoryItem,
  features: PermissionHistoryPanelProps["features"],
) {
  const currentChanges = features.flatMap((feature) => {
    const beforeOverride = item.old_overrides[feature.code] ?? "inherit";
    const afterOverride = item.new_overrides[feature.code] ?? "inherit";
    const before = item.old_effective[feature.code];
    const after = item.new_effective[feature.code];
    if (beforeOverride === afterOverride && before === after) return [];
    const effectiveChange =
      before === after
        ? `effective access remains ${displayEffect(after)}`
        : `effective access ${displayEffect(before)} → ${displayEffect(after)}`;
    return [
      `${feature.name}: ${displayOverride(beforeOverride)} → ${displayOverride(afterOverride)} · ${effectiveChange}`,
    ];
  });

  const previousModelChanges = legacyHistoryFeatures.flatMap((feature) => {
    const hasLegacyValue =
      feature.code in item.old_overrides ||
      feature.code in item.new_overrides ||
      feature.code in item.old_effective ||
      feature.code in item.new_effective;
    if (!hasLegacyValue) return [];

    const beforeOverride = item.old_overrides[feature.code] ?? "inherit";
    const afterOverride = item.new_overrides[feature.code] ?? "inherit";
    const before = item.old_effective[feature.code];
    const after = item.new_effective[feature.code];
    if (beforeOverride === afterOverride && before === after) return [];

    const effectiveChange =
      before === undefined || after === undefined
        ? "effective access recorded under the previous permission model"
        : before === after
          ? `effective access remains ${displayEffect(after)}`
          : `effective access ${displayEffect(before)} → ${displayEffect(after)}`;
    return [
      `Legacy ${feature.name}: ${displayOverride(beforeOverride)} → ${displayOverride(afterOverride)} · ${effectiveChange}`,
    ];
  });

  return [...currentChanges, ...previousModelChanges];
}

const dateFormatter = new Intl.DateTimeFormat("en-PH", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Manila",
});

export function PermissionHistoryPanel({
  history,
  features,
}: PermissionHistoryPanelProps) {
  return (
    <section className="mb-5 min-w-0 rounded-openci-md border border-openci-border bg-openci-surface p-4 max-[680px]:p-[14px]">
      <div className="mb-3.5 flex items-start justify-between gap-3">
        <div>
          <h2 className="m-0 text-[15px] font-semibold tracking-[-0.015em]">
            Permission history
          </h2>
          <p className="mt-[3px] mb-0 text-[13px] text-openci-text-muted">
            Recent changes made by administrators.
          </p>
        </div>
      </div>
      {history.length === 0 ? (
        <p className="muted">No permission changes recorded.</p>
      ) : (
        <ol className="mt-3.5 mb-3.5 grid list-none gap-2 p-0">
          {history.map((item) => {
            const changes = changesFor(item, features);
            return (
              <li
                className="grid gap-1 border-t border-openci-border py-2.5"
                key={item.id}
              >
                <div className="flex flex-wrap justify-between gap-x-4 gap-y-1">
                  <strong>{item.actor_name ?? "Former administrator"}</strong>
                  <time
                    className="text-[13px] text-openci-text-muted"
                    dateTime={item.created_at}
                  >
                    {dateFormatter.format(new Date(item.created_at))}
                  </time>
                </div>
                <p className="m-0 text-[13px] text-openci-text-muted">
                  {changes.length
                    ? changes.join(" · ")
                    : "Overrides updated; effective access did not change."}
                </p>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
