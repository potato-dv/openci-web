import type { LucideIcon } from "lucide-react";
import { CalendarClock, MapPinCheck, MapPinned, UserRound } from "lucide-react";
import type {
  Investigation,
  InvestigationLocation,
  NewInvestigation,
} from "@/types/api";
import {
  InvestigationDetailFields,
  SubjectFields,
} from "@/features/investigations/components/InvestigationForm";
import { PhilippineAddressFields } from "@/features/investigations/components/PhilippineAddressFields";
import {
  LocationPicker,
  type ConfirmedPoint,
} from "@/components/map/LocationPicker";
import { PLANNING_ENABLED } from "@/config";

type Props = {
  token: string;
  value: NewInvestigation;
  onChange: (value: NewInvestigation) => void;
  investigation: Investigation;
  existingPoint: InvestigationLocation | null;
  addressChanged: boolean;
  point: ConfirmedPoint | null;
  onPointChange: (point: ConfirmedPoint) => void;
  onPointEdit: () => void;
};

const editCardClass =
  "min-w-0 rounded-xl border border-openci-border bg-openci-surface p-4 md:p-6";

function EditSectionHeading({
  id,
  title,
  description,
  icon: Icon,
  tone,
}: {
  id: string;
  title: string;
  description: string;
  icon: LucideIcon;
  tone: "indigo" | "teal" | "blue";
}) {
  const iconTone = {
    indigo: "bg-openci-surface-selected text-openci-accent-strong",
    teal: "bg-openci-success-surface text-openci-success",
    blue: "bg-openci-info-surface text-openci-info",
  }[tone];

  return (
    <header className="mb-5 flex min-w-0 items-start gap-3 border-b border-openci-border pb-4">
      <span
        aria-hidden="true"
        className={`grid size-10 shrink-0 place-items-center rounded-lg ${iconTone}`}
      >
        <Icon size={19} strokeWidth={1.9} />
      </span>
      <div className="min-w-0 pt-0.5">
        <h2
          id={id}
          className="mb-1 text-base leading-snug font-semibold tracking-[-0.015em] text-openci-text"
        >
          {title}
        </h2>
        <p className="m-0 max-w-[68ch] text-[13px] leading-relaxed text-openci-text-muted">
          {description}
        </p>
      </div>
    </header>
  );
}

export function InvestigationEditSections({
  token,
  value,
  onChange,
  investigation,
  existingPoint,
  addressChanged,
  point,
  onPointChange,
  onPointEdit,
}: Props) {
  return (
    <div className="investigation-edit-sections grid min-w-0 grid-cols-1 items-stretch gap-4 xl:grid-cols-2">
      <section
        className={`${editCardClass} investigation-edit-personal`}
        aria-labelledby="edit-personal-title"
      >
        <EditSectionHeading
          id="edit-personal-title"
          title="Personal information"
          description="Update the name recorded for this investigation."
          icon={UserRound}
          tone="indigo"
        />
        <fieldset className="m-0 min-w-0 border-0 p-0">
          <legend className="sr-only">Personal information</legend>
          <SubjectFields value={value} onChange={onChange} paired />
        </fieldset>
      </section>

      <section className={editCardClass} aria-labelledby="edit-visit-title">
        <EditSectionHeading
          id="edit-visit-title"
          title="Visit requirements"
          description="Set priority, expected visit length, and an optional scheduling window."
          icon={CalendarClock}
          tone="teal"
        />
        <fieldset className="m-0 min-w-0 border-0 p-0">
          <legend className="sr-only">Visit requirements</legend>
          <InvestigationDetailFields value={value} onChange={onChange} />
        </fieldset>
      </section>

      <section
        className={`${editCardClass} col-span-full`}
        aria-labelledby="edit-address-title"
      >
        <EditSectionHeading
          id="edit-address-title"
          title="Investigation address"
          description="Keep the structured address accurate for field visits and route planning."
          icon={MapPinned}
          tone="teal"
        />
        <PhilippineAddressFields
          token={token}
          value={value}
          onChange={onChange}
          presentation="embedded"
        />
      </section>

      {PLANNING_ENABLED && (
        <section
          className={`${editCardClass} col-span-full`}
          aria-labelledby="edit-location-title"
        >
          <EditSectionHeading
            id="edit-location-title"
            title="Location confirmation"
            description="Confirm the map point used by route planning. Changing the address clears the current point until you confirm a new one."
            icon={MapPinCheck}
            tone="blue"
          />
          <LocationPicker
            key={`${value.region_code}:${value.street}:${value.barangay_code}`}
            token={token}
            initial={
              point ??
              (!addressChanged && existingPoint
                ? {
                    ...existingPoint,
                    label: investigation.address_display,
                  }
                : null)
            }
            initialQuery={[value.house_number, value.street, "Philippines"]
              .filter(Boolean)
              .join(", ")}
            onConfirm={onPointChange}
            onDirty={onPointEdit}
          />
        </section>
      )}
    </div>
  );
}
