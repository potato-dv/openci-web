import type {
  InvestigationOutcome,
  OccupancyStatus,
  ReportInput,
  VisitOutcome,
} from "@/types/api";

type ReportFormFieldsProps = {
  form: ReportInput;
  disabled: boolean;
  onChange: <K extends keyof ReportInput>(
    key: K,
    value: ReportInput[K],
  ) => void;
};

const fieldLabelClassName =
  "grid min-w-0 gap-1.5 text-[13px] font-medium text-openci-text-muted";

export function ReportFormFields({
  form,
  disabled,
  onChange,
}: ReportFormFieldsProps) {
  return (
    <>
      <div className="mb-4 border-b border-openci-border pb-4">
        <h4 className="mb-0 text-sm font-semibold text-openci-text">Visit and outcome</h4>
        <p className="mt-1 mb-0 text-xs text-openci-text-muted">Record what happened at the location before describing your findings.</p>
      </div>
      <div className="mb-5 grid grid-cols-2 gap-x-4 gap-y-4 max-[767px]:grid-cols-1">
        <label className={fieldLabelClassName}>
          Visit outcome
          <select
            value={form.visit_outcome ?? ""}
            onChange={(event) =>
              onChange(
                "visit_outcome",
                (event.target.value || null) as VisitOutcome | null,
              )
            }
            disabled={disabled}
          >
            <option value="">Select visit outcome</option>
            <option value="visited">Visited</option>
            <option value="no_access">No access</option>
            <option value="unable_to_locate">Unable to locate</option>
          </select>
        </label>
        <label className={fieldLabelClassName}>
          Investigation outcome
          <select
            value={form.outcome ?? ""}
            onChange={(event) =>
              onChange(
                "outcome",
                (event.target.value || null) as InvestigationOutcome | null,
              )
            }
            disabled={disabled}
          >
            <option value="">Select investigation outcome</option>
            <option value="verified">Verified</option>
            <option value="not_verified">Not verified</option>
            <option value="unable_to_verify">Unable to verify</option>
            <option value="inconclusive">Inconclusive</option>
          </select>
        </label>
        <label className={fieldLabelClassName}>
          Verified address{" "}
          <span className="optional-label">
            Required when outcome is Verified
          </span>
          <input
            value={form.verified_address ?? ""}
            onChange={(event) =>
              onChange("verified_address", event.target.value || null)
            }
            maxLength={500}
            disabled={disabled}
          />
        </label>
        <label className={fieldLabelClassName}>
          Occupancy status <span className="optional-label">Optional</span>
          <select
            value={form.occupancy_status ?? ""}
            onChange={(event) =>
              onChange(
                "occupancy_status",
                (event.target.value || null) as OccupancyStatus | null,
              )
            }
            disabled={disabled}
          >
            <option value="">Select occupancy status</option>
            <option value="occupied">Occupied</option>
            <option value="vacant">Vacant</option>
            <option value="unknown">Unknown</option>
            <option value="not_applicable">Not applicable</option>
          </select>
        </label>
        <label className={fieldLabelClassName}>
          Visit date and time · Philippine time{" "}
          <span className="optional-label">
            Required for Visited or No access
          </span>
          <input
            type="datetime-local"
            value={form.visited_at ?? ""}
            onChange={(event) =>
              onChange("visited_at", event.target.value || null)
            }
            disabled={disabled}
          />
        </label>
      </div>
      <div className="grid gap-4 border-t border-openci-border pt-5">
        <h4 className="mb-0 text-sm font-semibold text-openci-text">Observations and findings</h4>
        <div className="grid gap-1.5">
          <label htmlFor="property-condition">Property condition <span className="optional-label">Optional</span></label>
          <textarea
            id="property-condition"
            value={form.property_condition ?? ""}
            onChange={(event) => onChange("property_condition", event.target.value || null)}
            placeholder="Describe relevant property observations"
            disabled={disabled}
          />
        </div>
        <div className="grid gap-1.5">
          <label htmlFor="interaction-notes">Interaction notes <span className="optional-label">Optional</span></label>
          <textarea
            id="interaction-notes"
            value={form.interaction_notes ?? ""}
            onChange={(event) => onChange("interaction_notes", event.target.value || null)}
            placeholder="Record factual notes about the interaction"
            disabled={disabled}
          />
        </div>
        <div className="grid gap-1.5">
          <label className="report-findings-field-label" htmlFor="report-content">
            Detailed findings
            <span>Required · describe what you observed at the location</span>
          </label>
          <textarea
            id="report-content"
            className="report-editor report-findings-input"
            value={form.content}
            onChange={(event) => onChange("content", event.target.value)}
            placeholder="Describe the investigation findings..."
            maxLength={20_000}
            disabled={disabled}
          />
        </div>
      </div>
    </>
  );
}
