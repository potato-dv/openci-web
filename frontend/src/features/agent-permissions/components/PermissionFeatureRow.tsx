import { CheckCircle2, CircleX } from "lucide-react";
import type { AgentPermissionFeature } from "@/types/api";

type PermissionChoice = "allow" | "deny";

type PermissionFeatureRowProps = {
  feature: AgentPermissionFeature;
  selectedOverride: PermissionChoice;
  hasPendingChange: boolean;
  onOverrideChange: (effect: PermissionChoice) => void;
};

function displayEffect(value: boolean) {
  return value ? "Allowed" : "Denied";
}

export function PermissionFeatureRow({
  feature,
  selectedOverride,
  hasPendingChange,
  onOverrideChange,
}: PermissionFeatureRowProps) {
  const selectedAllowed = selectedOverride === "allow";

  return (
    <article className="grid min-w-0 grid-cols-[minmax(0,1fr)_minmax(10rem,14rem)] items-center gap-x-6 gap-y-3 py-4 first:pt-0 last:pb-0 max-[680px]:grid-cols-1">
      <div className="min-w-0">
        <h3 className="m-0 text-sm font-semibold text-[#1a2d4c]">{feature.name}</h3>
        <p className="mb-0 mt-1 text-[13px] leading-[1.45] text-[#63748e]">
          {feature.description}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[#63748e]">
          <span className={`inline-flex items-center gap-1.5 font-medium ${selectedAllowed ? "text-emerald-700" : "text-rose-700"}`}>
            {selectedAllowed ? (
              <CheckCircle2 size={14} aria-hidden="true" />
            ) : (
              <CircleX size={14} aria-hidden="true" />
            )}
            {hasPendingChange ? "Selected access" : "Effective access"}: {displayEffect(selectedAllowed)}
          </span>
        </div>
        {hasPendingChange && (
          <p className="mb-0 mt-1.5 text-xs font-medium text-amber-700">
            Unsaved selection
          </p>
        )}
      </div>

      <fieldset className="m-0 grid min-w-0 grid-cols-2 gap-1 rounded-lg border border-[#dce4ef] bg-[#f5f7fa] p-1 max-[680px]:w-full sm:min-w-[11rem]">
        <legend className="sr-only">{feature.name} access</legend>
        {(["allow", "deny"] as const).map((effect) => {
          const checked = selectedOverride === effect;
          const label = effect === "allow" ? "Allow" : "Deny";
          return (
            <label className="relative flex min-w-0 cursor-pointer" key={effect}>
              <input
                className="peer sr-only"
                type="radio"
                name={`permission-${feature.code}`}
                value={effect}
                aria-label={`${feature.name} permission: ${label}`}
                checked={checked}
                onChange={() => onOverrideChange(effect)}
              />
              <span className="flex min-h-9 w-full items-center justify-center rounded-md px-3 text-[13px] font-medium text-[#526784] transition-colors peer-checked:bg-white peer-checked:text-[#1a2d4c] peer-checked:shadow-sm peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-[#3261c5]">
                {label}
              </span>
            </label>
          );
        })}
      </fieldset>
    </article>
  );
}
