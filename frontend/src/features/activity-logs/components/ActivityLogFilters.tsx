import { useState } from "react";
import { ListFilter } from "lucide-react";

import { Drawer, Button } from "@/components/ui/Primitives";
import { WorkspaceSearchField } from "@/components/data/WorkspaceSearchField";
import { WorkspaceSelect } from "@/components/ui/WorkspaceSelect";
import type { ActivityLogFilterOptions } from "@/types/api";

const NARROWING_KEYS = [
  "q",
  "action",
  "actor",
  "object_type",
  "object_id",
  "from",
  "to",
];

const fieldClassName = "grid min-w-0 gap-1.5";
const inputClassName = "h-10 rounded-lg border border-[#d6e0ed] bg-white px-3 text-[12px] text-[#283b5a] shadow-[0_1px_2px_rgba(22,43,77,0.03)] outline-none focus:border-[#3565c7] focus:ring-2 focus:ring-[#3565c7]/15";

function humanize(value: string) {
  return value
    .replaceAll(".", " ")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function activityFilterCount(params: URLSearchParams) {
  return NARROWING_KEYS.filter((key) => Boolean(params.get(key)?.trim())).length;
}

export function ActivityLogFilters({
  appliedParams,
  options,
  optionsLoading,
  onApply,
}: {
  appliedParams: URLSearchParams;
  options: ActivityLogFilterOptions | null;
  optionsLoading: boolean;
  onApply: (params: URLSearchParams) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draftParams, setDraftParams] = useState(
    () => new URLSearchParams(appliedParams),
  );
  const [portalContainer, setPortalContainer] =
    useState<HTMLDivElement | null>(null);

  function openFilters() {
    setDraftParams(new URLSearchParams(appliedParams));
    setOpen(true);
  }

  function cancel() {
    setDraftParams(new URLSearchParams(appliedParams));
    setOpen(false);
  }

  function updateDraft(name: string, value: string) {
    setDraftParams((current) => {
      const next = new URLSearchParams(current);
      if (value) next.set(name, value);
      else next.delete(name);
      return next;
    });
  }

  function clearDraft() {
    setDraftParams((current) => {
      const next = new URLSearchParams(current);
      for (const key of NARROWING_KEYS) next.delete(key);
      next.delete("page");
      return next;
    });
  }

  function apply() {
    const from = draftParams.get("from") ?? "";
    const to = draftParams.get("to") ?? "";
    if (from && to && from > to) return;
    const next = new URLSearchParams(draftParams);
    next.delete("page");
    onApply(next);
    setOpen(false);
  }

  const activeCount = activityFilterCount(appliedParams);
  const draftCount = activityFilterCount(draftParams);
  const from = draftParams.get("from") ?? "";
  const to = draftParams.get("to") ?? "";
  const dateError = from && to && from > to
    ? "From date cannot be later than To date."
    : "";
  const selectDisabled = optionsLoading && !options;

  return (
    <>
      <Button
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={openFilters}
      >
        <ListFilter size={16} aria-hidden="true" />
        Filters
        {activeCount > 0 && (
          <span className="grid min-w-5 place-items-center rounded-full bg-[#e5edff] px-1.5 text-[11px] font-semibold tabular-nums text-[#2857b0]">
            {activeCount}
          </span>
        )}
      </Button>
      <Drawer
        title="Filter activity logs"
        open={open}
        onClose={cancel}
        contentRef={setPortalContainer}
      >
        <div className="grid gap-5">
          <p className="m-0 text-[13px] leading-5 text-openci-text-muted">
            Select filters, then apply them together to refresh the audit trail.
          </p>

          <div className="grid gap-4">
            <WorkspaceSearchField
              className={fieldClassName}
              label="Search logs"
              value={draftParams.get("q") ?? ""}
              onChange={(value) => updateDraft("q", value)}
              placeholder="Actor, action, record, or details"
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <WorkspaceSelect
                label="Action"
                value={draftParams.get("action") ?? ""}
                onValueChange={(value) => updateDraft("action", value)}
                options={[
                  { value: "", label: "All actions" },
                  ...(options?.actions.map((action) => ({
                    value: action,
                    label: humanize(action),
                  })) ?? []),
                ]}
                disabled={selectDisabled}
                portalContainer={portalContainer}
              />
              <WorkspaceSelect
                label="Actor"
                value={draftParams.get("actor") ?? ""}
                onValueChange={(value) => updateDraft("actor", value)}
                options={[
                  { value: "", label: "All actors" },
                  ...(options?.actors.map((actor) => ({
                    value: actor.id == null ? "system" : String(actor.id),
                    label: actor.name,
                  })) ?? []),
                ]}
                disabled={selectDisabled}
                portalContainer={portalContainer}
              />
              <WorkspaceSelect
                label="Record type"
                value={draftParams.get("object_type") ?? ""}
                onValueChange={(value) => updateDraft("object_type", value)}
                options={[
                  { value: "", label: "All records" },
                  ...(options?.object_types.map((objectType) => ({
                    value: objectType,
                    label: humanize(objectType),
                  })) ?? []),
                ]}
                disabled={selectDisabled}
                portalContainer={portalContainer}
              />
              <label className={fieldClassName}>
                <span className="text-[11px] font-medium text-[#66758b]">Record ID</span>
                <input
                  className={inputClassName}
                  type="number"
                  min="1"
                  inputMode="numeric"
                  value={draftParams.get("object_id") ?? ""}
                  onChange={(event) => updateDraft("object_id", event.target.value)}
                  placeholder="Any ID"
                />
              </label>
              <label className={fieldClassName}>
                <span className="text-[11px] font-medium text-[#66758b]">From date</span>
                <input
                  className={inputClassName}
                  type="date"
                  value={from}
                  onChange={(event) => updateDraft("from", event.target.value)}
                />
              </label>
              <label className={fieldClassName}>
                <span className="text-[11px] font-medium text-[#66758b]">To date</span>
                <input
                  className={inputClassName}
                  type="date"
                  value={to}
                  onChange={(event) => updateDraft("to", event.target.value)}
                />
              </label>
              <WorkspaceSelect
                label="Sort by"
                value={draftParams.get("sort") ?? "created_at"}
                onValueChange={(value) => updateDraft("sort", value)}
                options={[
                  { value: "created_at", label: "Created date" },
                  { value: "action", label: "Action" },
                  { value: "actor", label: "Actor" },
                  { value: "object_type", label: "Record type" },
                  { value: "object_id", label: "Record ID" },
                ]}
                portalContainer={portalContainer}
              />
              <WorkspaceSelect
                label="Order"
                value={draftParams.get("direction") ?? "desc"}
                onValueChange={(value) => updateDraft("direction", value)}
                options={[
                  { value: "desc", label: "Newest first" },
                  { value: "asc", label: "Oldest first" },
                ]}
                portalContainer={portalContainer}
              />
            </div>
            {dateError && (
              <p className="m-0 text-xs font-medium text-openci-danger" role="alert">
                {dateError}
              </p>
            )}
          </div>

          <div className="flex flex-wrap justify-end gap-2 border-t border-openci-border pt-4">
            <Button onClick={clearDraft} disabled={draftCount === 0}>
              Clear filters
            </Button>
            <Button onClick={cancel}>Cancel</Button>
            <Button variant="primary" onClick={apply} disabled={Boolean(dateError)}>
              Apply filters
            </Button>
          </div>
        </div>
      </Drawer>
    </>
  );
}
