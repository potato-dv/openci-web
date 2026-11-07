export type AttemptReason =
  | "no_contact_person"
  | "nobody_at_location"
  | "requested_later_visit"
  | "other";

type NoContactAttemptFieldsProps = {
  reason: AttemptReason;
  notes: string;
  contactFrom: string;
  contactUntil: string;
  disabled: boolean;
  onReasonChange: (reason: AttemptReason) => void;
  onNotesChange: (notes: string) => void;
  onContactFromChange: (value: string) => void;
  onContactUntilChange: (value: string) => void;
};

const fieldLabelClassName =
  "grid min-w-0 gap-[5px] text-xs font-[550] text-openci-text-muted";

export function NoContactAttemptFields({
  reason,
  notes,
  contactFrom,
  contactUntil,
  disabled,
  onReasonChange,
  onNotesChange,
  onContactFromChange,
  onContactUntilChange,
}: NoContactAttemptFieldsProps) {
  return (
    <div className="mb-3 grid grid-cols-2 gap-2.5 max-[767px]:grid-cols-1">
      <label className={fieldLabelClassName}>
        Unable to proceed
        <select
          value={reason}
          onChange={(event) =>
            onReasonChange(event.target.value as AttemptReason)
          }
          disabled={disabled}
        >
          <option value="no_contact_person">No contact person available</option>
          <option value="nobody_at_location">Nobody at the location</option>
          <option value="requested_later_visit">
            Contact requested a later visit
          </option>
          <option value="other">Other</option>
        </select>
      </label>
      <label className={fieldLabelClassName}>
        Notes{reason === "other" ? " · required" : " · optional"}
        <input
          value={notes}
          onChange={(event) => onNotesChange(event.target.value)}
          maxLength={4000}
          disabled={disabled}
        />
      </label>
      <label className={fieldLabelClassName}>
        Contact available from · Philippine time
        <input
          type="datetime-local"
          value={contactFrom}
          onChange={(event) => onContactFromChange(event.target.value)}
          disabled={disabled}
        />
      </label>
      <label className={fieldLabelClassName}>
        Contact available until · Philippine time
        <input
          type="datetime-local"
          value={contactUntil}
          onChange={(event) => onContactUntilChange(event.target.value)}
          disabled={disabled}
        />
      </label>
    </div>
  );
}
