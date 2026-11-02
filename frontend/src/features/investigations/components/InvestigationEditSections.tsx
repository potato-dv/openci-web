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
    <div className="investigation-edit-sections">
      <fieldset className="investigation-edit-section">
        <legend>Personal information</legend>
        <p className="investigation-edit-section-copy">
          Update the name recorded for this investigation.
        </p>
        <SubjectFields value={value} onChange={onChange} paired />
      </fieldset>

      <fieldset className="investigation-edit-section">
        <legend>Visit requirements</legend>
        <p className="investigation-edit-section-copy">
          Set the priority, expected visit length, and any scheduling window.
        </p>
        <InvestigationDetailFields value={value} onChange={onChange} />
      </fieldset>

      <PhilippineAddressFields
        token={token}
        value={value}
        onChange={onChange}
      />

      {PLANNING_ENABLED && (
        <section className="investigation-edit-section investigation-edit-location">
          <h2>Location confirmation</h2>
          <p className="investigation-edit-section-copy">
            Route planning uses confirmed coordinates. Changing the address
            clears the existing point until you confirm a new one.
          </p>
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
