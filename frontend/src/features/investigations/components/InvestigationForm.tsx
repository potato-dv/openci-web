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
  const labels = [
    "Subject",
    "Investigation details",
    "Philippine address",
    "Location confirmation",
    "Review and save",
  ];
  return (
    <nav aria-label="Investigation form progress" className="mb-5 overflow-x-auto rounded-xl border border-[#dfe7f1] bg-white p-2">
      <p className="mb-1 px-2 text-xs font-semibold text-[#315cb0] md:hidden">Step {step + 1} of {labels.length} · {labels[step]}</p>
      <ol className="m-0 grid list-none grid-cols-5 gap-1 p-0 md:min-w-[700px]">
        {labels.map((label, index) => (
          <li key={label} className="min-w-0">
            <button
              type="button"
              aria-current={index === step ? "step" : undefined}
              disabled={index > completed}
              onClick={() => onStep(index)}
              className={`flex min-h-[46px] w-full items-center justify-center gap-2 rounded-lg border-0 px-1 text-left text-[12px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45 md:min-h-[54px] md:justify-start md:px-3 ${index === step ? "bg-[#eaf1ff] text-[#2452a4]" : "bg-transparent text-[#697c98] hover:bg-[#f4f7fb]"}`}
            >
              <span className={`grid size-7 shrink-0 place-items-center rounded-full text-xs font-semibold ${index === step ? "bg-[#3261c5] text-white" : index < completed ? "bg-[#dce9ff] text-[#2859b3]" : "border border-[#cad5e4] text-[#7a8ba5]"}`}>{index + 1}</span>
              <span className="hidden leading-tight md:inline">{label}</span>
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}
