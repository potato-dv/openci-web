import type { NewInvestigation } from "@/types/api";
import { FormField } from "@/components/ui/Primitives";
export function SubjectFields({
  value,
  onChange,
  paired = false,
}: {
  value: NewInvestigation;
  onChange: (value: NewInvestigation) => void;
  paired?: boolean;
}) {
  return (
    <div
      className={`subject-name-grid${paired ? " subject-name-grid-paired" : ""}`}
    >
      <FormField
        label="First name"
        autoComplete="given-name"
        required
        maxLength={255}
        value={value.first_name}
        onChange={(event) =>
          onChange({ ...value, first_name: event.target.value })
        }
      />
      <FormField
        label="Middle name (optional)"
        autoComplete="additional-name"
        maxLength={255}
        value={value.middle_name ?? ""}
        onChange={(event) =>
          onChange({ ...value, middle_name: event.target.value || null })
        }
      />
      <FormField
        label="Last name"
        autoComplete="family-name"
        required
        maxLength={255}
        value={value.last_name}
        onChange={(event) =>
          onChange({ ...value, last_name: event.target.value })
        }
      />
    </div>
  );
}
export function InvestigationDetailFields({
  value,
  onChange,
}: {
  value: NewInvestigation;
  onChange: (value: NewInvestigation) => void;
}) {
  const localTime = (value: string | null) =>
    value
      ? new Intl.DateTimeFormat("sv-SE", {
          timeZone: "Asia/Manila",
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          hourCycle: "h23",
        })
          .format(new Date(value))
          .replace(" ", "T")
      : "";
  return (
    <div className="form-grid investigation-detail-grid">
      <label>
        Priority
        <select
          value={value.priority}
          onChange={(event) =>
            onChange({
              ...value,
              priority: event.target.value as NewInvestigation["priority"],
            })
          }
        >
          <option value="normal">Normal</option>
          <option value="high">High</option>
          <option value="urgent">Urgent</option>
        </select>
      </label>
      <FormField
        label="Estimated visit duration (minutes)"
        type="number"
        min={5}
        max={480}
        required
        value={value.service_duration_seconds / 60}
        onChange={(event) =>
          onChange({
            ...value,
            service_duration_seconds: Number(event.target.value) * 60,
          })
        }
      />
      <FormField
        label="Earliest visit (optional)"
        type="datetime-local"
        hint="Philippine time (UTC+8)"
        value={localTime(value.visit_not_before_at)}
        onChange={(event) =>
          onChange({
            ...value,
            visit_not_before_at: event.target.value
              ? `${event.target.value}:00+08:00`
              : null,
          })
        }
      />
      <FormField
        label="Completion deadline (optional)"
        type="datetime-local"
        hint="Must be after the earliest visit"
        value={localTime(value.visit_due_at)}
        onChange={(event) =>
          onChange({
            ...value,
            visit_due_at: event.target.value
              ? `${event.target.value}:00+08:00`
              : null,
          })
        }
      />
    </div>
  );
}
export function InvestigationFormStepper({
  step,
  onStep,
  completed,
}: {
  step: number;
  onStep: (step: number) => void;
  completed: number;
}) {
  return (
    <nav aria-label="Investigation form progress">
      <ol className="form-stepper">
        {[
          "Subject",
          "Investigation details",
          "Philippine address",
          "Location confirmation",
          "Review and save",
        ].map((label, index) => (
          <li key={label}>
            <button
              type="button"
              aria-current={index === step ? "step" : undefined}
              disabled={index > completed}
              onClick={() => onStep(index)}
            >
              <span>{index + 1}</span>
              {label}
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}
