import { CheckCircle2, CircleX } from "lucide-react";
import type {
  AgentPermissionEffect,
  AgentPermissionFeature,
} from "@/types/api";

type PermissionFeatureRowProps = {
  feature: AgentPermissionFeature;
  selectedOverride: AgentPermissionEffect;
  onOverrideChange: (effect: AgentPermissionEffect) => void;
};

function displayEffect(value: boolean) {
  return value ? "Allowed" : "Denied";
}

function displayOverride(value: AgentPermissionEffect) {
  if (value === "allow") return "Allow";
  if (value === "deny") return "Deny";
  return "Use default";
}

export function PermissionFeatureRow({
  feature,
  selectedOverride,
  onOverrideChange,
}: PermissionFeatureRowProps) {
  const hasPendingChange = (feature.override ?? "inherit") !== selectedOverride;

  return (
    <article className="grid min-w-0 grid-cols-[minmax(0,1fr)_minmax(10rem,14rem)] items-center gap-x-6 gap-y-3 border-t border-openci-border py-4 last:border-b max-[680px]:grid-cols-1">
      <div className="min-w-0">
        <h3 className="m-0 text-sm font-semibold">{feature.name}</h3>
        <p className="mt-1 mb-0 text-[13px] leading-[1.45] text-openci-text-muted">
          {feature.description}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-openci-text-muted">
          <span>Agent default: {displayEffect(feature.default_allowed)}</span>
          <span className="inline-flex items-center gap-1.5 font-medium text-openci-text">
            {feature.effective_allowed ? (
              <CheckCircle2 size={15} className="text-openci-success" aria-hidden="true" />
            ) : (
              <CircleX size={15} className="text-openci-danger" aria-hidden="true" />
            )}
            Effective: {displayEffect(feature.effective_allowed)}
          </span>
        </div>
        {hasPendingChange && (
          <p className="history-access-pending mt-2">
            Unsaved selection: {displayOverride(selectedOverride)}
          </p>
        )}
      </div>
      <label className="grid min-w-0 gap-1 text-xs font-semibold text-openci-text-muted">
        <span>Override</span>
        <select
          aria-label={`${feature.name} permission`}
          className="min-h-[38px] w-full text-[13px] max-[680px]:min-h-11"
          value={selectedOverride}
          onChange={(event) =>
            onOverrideChange(event.target.value as AgentPermissionEffect)
          }
        >
          <option value="inherit">Use default</option>
          <option value="allow">Allow</option>
          <option value="deny">Deny</option>
        </select>
      </label>
    </article>
  );
}
