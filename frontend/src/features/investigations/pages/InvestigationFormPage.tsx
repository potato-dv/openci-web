import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Link, useNavigate, useParams } from "react-router";
import { FilePenLine } from "lucide-react";
import { useSession } from "@/app/session";
import {
  confirmInvestigationLocation,
  createInvestigation,
  getInvestigation,
  getInvestigationLocation,
  updateInvestigation,
} from "@/features/investigations/api";
import { getBarangays, getCities, getRegions } from "@/features/locations/api";
import { useResource } from "@/hooks/useResource";
import { useDirtyForm } from "@/features/investigations/hooks/useDirtyForm";
import type {
  Investigation,
  NewInvestigation,
  InvestigationLocation,
} from "@/types/api";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button, InlineAlert, Skeleton } from "@/components/ui/Primitives";
import { PriorityBadge } from "@/components/ui/PriorityBadge";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  InvestigationDetailFields,
  InvestigationFormStepper,
  SubjectFields,
} from "@/features/investigations/components/InvestigationForm";
import { PhilippineAddressFields } from "@/features/investigations/components/PhilippineAddressFields";
import { InvestigationEditSections } from "@/features/investigations/components/InvestigationEditSections";
import {
  LocationPicker,
  type ConfirmedPoint,
} from "@/components/map/LocationPicker";
import { investigationChanges } from "@/features/investigations/components/investigationChanges";
import { investigationStepError } from "@/features/investigations/components/investigationValidation";
import { PLANNING_ENABLED } from "@/config";
const blank: NewInvestigation = {
  first_name: "",
  middle_name: null,
  last_name: "",
  house_number: "",
  unit_floor_building_name: "",
  street: "",
  subdivision_village_purok: "",
  region_code: "",
  province_code: "",
  city_municipality_code: "",
  barangay_code: "",
  postal_code: "",
  priority: "normal",
  service_duration_seconds: 2700,
  visit_not_before_at: null,
  visit_due_at: null,
};
function initialValues(item: Investigation | null): NewInvestigation {
  if (!item) return blank;
  return {
    ...blank,
    ...Object.fromEntries(
      Object.entries(blank).map(([key, fallback]) => [
        key,
        item[key as keyof Investigation] ?? fallback,
      ]),
    ),
  } as NewInvestigation;
}
function AddressReview({
  token,
  value,
}: {
  token: string;
  value: NewInvestigation;
}) {
  const resource = useResource(
    useCallback(async () => {
      const [regions, cities, barangays] = await Promise.all([
        getRegions(token),
        getCities(token, value.region_code, value.province_code || undefined),
        getBarangays(token, value.city_municipality_code),
      ]);
      return [
        value.house_number,
        value.unit_floor_building_name,
        value.street,
        value.subdivision_village_purok,
        barangays.find((item) => item.code === value.barangay_code)?.name,
        cities.find((item) => item.code === value.city_municipality_code)?.name,
        regions.find((item) => item.code === value.region_code)?.name,
        value.postal_code,
      ]
        .filter(Boolean)
        .join(", ");
    }, [token, value]),
  );
  return (
    <>
      {resource.loading ? (
        "Loading address…"
      ) : resource.error ? (
        <InlineAlert onRetry={resource.refresh}>{resource.error}</InlineAlert>
      ) : (
        resource.data
      )}
    </>
  );
}
function Editor({
  investigation,
  existingPoint,
}: {
  investigation: Investigation | null;
  existingPoint: InvestigationLocation | null;
}) {
  const { token } = useSession();
  const navigate = useNavigate();
  const [value, setValue] = useState(() => initialValues(investigation));
  const [step, setStep] = useState(0);
  const [completed, setCompleted] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [point, setPoint] = useState<ConfirmedPoint | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const lock = useRef(false);
  const formRef = useRef<HTMLFormElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    headingRef.current?.focus();
  }, [step]);
  const original = initialValues(investigation);
  const addressChanged = [
    "house_number",
    "street",
    "unit_floor_building_name",
    "subdivision_village_purok",
    "region_code",
    "province_code",
    "city_municipality_code",
    "barangay_code",
    "postal_code",
  ].some(
    (key) =>
      value[key as keyof NewInvestigation] !==
      original[key as keyof NewInvestigation],
  );
  const retainedLocation = Boolean(
    investigation?.location_confirmed && !addressChanged,
  );
  useDirtyForm(dirty && !busy);
  function change(next: NewInvestigation) {
    const addressChanged = [
      "house_number",
      "street",
      "unit_floor_building_name",
      "subdivision_village_purok",
      "region_code",
      "province_code",
      "city_municipality_code",
      "barangay_code",
      "postal_code",
    ].some(
      (key) =>
        next[key as keyof NewInvestigation] !==
        value[key as keyof NewInvestigation],
    );
    if (addressChanged) setPoint(null);
    setValue(next);
    if (step < 3) setCompleted((current) => Math.min(current, step));
    setDirty(true);
    setError("");
  }
  function validateStep() {
    const message = investigationStepError(value, step);
    setError(message);
    return Boolean(formRef.current?.reportValidity()) && !message;
  }
  function next() {
    if (!validateStep()) return;
    const nextStep = step === 2 && !PLANNING_ENABLED ? 4 : step + 1;
    setStep(nextStep);
    setCompleted(Math.max(completed, nextStep));
    setError("");
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!investigation && step < 4) {
      next();
      return;
    }
    for (let index = 0; index < 3; index += 1) {
      const message = investigationStepError(value, index);
      if (message) {
        setStep(index);
        setCompleted(index);
        setError(message);
        return;
      }
    }
    if (investigation && !formRef.current?.reportValidity()) {
      setError("Review the highlighted fields before saving.");
      return;
    }
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      const saved = investigation
        ? await updateInvestigation(
            token,
            investigation.id,
            investigationChanges(initialValues(investigation), value),
          )
        : await createInvestigation(token, value);
      if (point) {
        try {
          await confirmInvestigationLocation(token, saved.id, point);
        } catch {
          setDirty(false);
          navigate(`/investigations/${saved.id}`, {
            replace: true,
            state: { locationError: true, locationDraft: point },
          });
          return;
        }
      }
      setDirty(false);
      navigate(`/investigations/${saved.id}`, { replace: true });
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "The investigation could not be saved. Check the form and retry.",
      );
    } finally {
      setBusy(false);
      lock.current = false;
    }
  }
  return (
    <>
      <PageHeader
        title={investigation ? "Edit investigation" : "New investigation"}
        description={
          investigation
            ? "Update subject details, visit timing, address, and map location."
            : "Confirm the subject, address, and visit requirements before saving."
        }
        actions={
          investigation ? (
            <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto sm:justify-end">
              <span className="inline-flex min-w-0 max-w-full items-center gap-2 rounded-lg border border-openci-border bg-openci-surface px-3 py-2 text-openci-text">
                <span className="shrink-0 text-xs font-medium text-openci-text-muted">
                  Reference
                </span>
                <code
                  className="max-w-[220px] truncate font-mono text-xs text-openci-text"
                  title={investigation.reference_number}
                >
                  {investigation.reference_number}
                </code>
              </span>
              <StatusBadge
                status={investigation.status}
                reopenOn={investigation.reopen_on}
              />
              <PriorityBadge priority={investigation.priority} />
            </div>
          ) : undefined
        }
        parent={{
          to: investigation
            ? `/investigations/${investigation.id}`
            : "/investigations",
          label: investigation ? "Investigation" : "Investigations",
        }}
      />
      <div
        className={`form-workspace${investigation ? " form-workspace-edit" : ""}`}
      >
        {!investigation && (
          <InvestigationFormStepper
            step={step}
            onStep={(target) => {
              if (target > step && !validateStep()) return;
              setError("");
              setStep(target);
            }}
            completed={completed}
          />
        )}
        <form
          ref={formRef}
          className={`content-card investigation-form${investigation ? " investigation-edit-form" : ""}`}
          onSubmit={save}
        >
          {investigation ? (
            <>
              <div className="investigation-edit-heading flex items-center gap-3 rounded-xl border border-openci-border bg-openci-surface p-4 md:p-5">
                <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-openci-surface-selected text-openci-accent-strong">
                  <FilePenLine size={20} strokeWidth={1.9} aria-hidden="true" />
                </span>
                <div className="min-w-0">
                  <h2
                    ref={headingRef}
                    tabIndex={-1}
                    className="mb-0 w-fit max-w-full text-base leading-tight font-semibold tracking-[-0.015em] text-openci-text"
                  >
                    Investigation details
                  </h2>
                  <p className="mt-1 mb-0 text-[13px] text-openci-text-muted">
                    Review the existing information and update only what needs
                    to change.
                  </p>
                </div>
              </div>
              {!investigation.first_name && (
                <InlineAlert variant="warning">
                  Confirm the name parts for this legacy subject:{" "}
                  {investigation.subject_name}
                </InlineAlert>
              )}
              <InvestigationEditSections
                token={token}
                value={value}
                onChange={change}
                investigation={investigation}
                existingPoint={existingPoint}
                addressChanged={addressChanged}
                point={point}
                onPointChange={(nextPoint) => {
                  setPoint(nextPoint);
                  setDirty(true);
                }}
                onPointEdit={() => {
                  setPoint(null);
                  setDirty(true);
                }}
              />
            </>
          ) : (
            <>
              <h2 ref={headingRef} tabIndex={-1}>
                {
                  [
                    "Subject information",
                    "Investigation details",
                    "Philippine address",
                    "Location confirmation",
                    "Review and save",
                  ][step]
                }
              </h2>
              {step === 0 && (
                <>
                  <p className="form-hint">
                    The investigation reference is generated automatically.
                  </p>
                  <SubjectFields value={value} onChange={change} />
                </>
              )}
              {step === 1 && (
                <InvestigationDetailFields value={value} onChange={change} />
              )}
              {step === 2 && (
                <PhilippineAddressFields
                  token={token}
                  value={value}
                  onChange={change}
                />
              )}
              {step === 3 && (
                <>
                  <p className="form-hint">
                    Location confirmation is optional. Route optimization
                    requires confirmed coordinates.
                  </p>
                  <LocationPicker
                    key={`${value.region_code}:${value.street}:${value.barangay_code}`}
                    token={token}
                    initial={point}
                    initialQuery={[
                      value.house_number,
                      value.street,
                      "Philippines",
                    ]
                      .filter(Boolean)
                      .join(", ")}
                    onConfirm={(point) => {
                      setPoint(point);
                      setDirty(true);
                    }}
                    onDirty={() => {
                      setPoint(null);
                      setDirty(true);
                    }}
                  />
                </>
              )}
            </>
          )}
          {step === 4 && (
            <>
              <dl className="review-summary">
                <div>
                  <dt>Subject</dt>
                  <dd>
                    {[value.first_name, value.middle_name, value.last_name]
                      .filter(Boolean)
                      .join(" ")}
                  </dd>
                </div>
                <div>
                  <dt>Address</dt>
                  <dd>
                    <AddressReview token={token} value={value} />
                  </dd>
                </div>
                <div>
                  <dt>Priority / visit duration</dt>
                  <dd>
                    {value.priority} · {value.service_duration_seconds / 60}{" "}
                    minutes
                  </dd>
                </div>
                <div>
                  <dt>Visit window · Philippine time</dt>
                  <dd>
                    {value.visit_not_before_at
                      ? new Date(value.visit_not_before_at).toLocaleString(
                          "en-PH",
                          { timeZone: "Asia/Manila" },
                        )
                      : "No earliest time"}{" "}
                    →{" "}
                    {value.visit_due_at
                      ? new Date(value.visit_due_at).toLocaleString("en-PH", {
                          timeZone: "Asia/Manila",
                        })
                      : "No deadline"}
                  </dd>
                </div>
                <div>
                  <dt>Location</dt>
                  <dd>
                    {point
                      ? `${point.latitude.toFixed(6)}, ${point.longitude.toFixed(6)} · confirmed selection`
                      : retainedLocation
                        ? "Existing location retained unless the address changes"
                        : "Unconfirmed"}
                  </dd>
                </div>
              </dl>
              {!point && !retainedLocation && (
                <InlineAlert variant="info">
                  You can save this investigation now. It will remain excluded
                  from route optimization until its location is confirmed.
                </InlineAlert>
              )}
            </>
          )}
          {error && <InlineAlert>{error}</InlineAlert>}
          <footer
            className={`form-footer${investigation ? " investigation-edit-footer" : ""}`}
          >
            <Link
              className="secondary-button"
              to={
                investigation
                  ? `/investigations/${investigation.id}`
                  : "/investigations"
              }
            >
              Cancel
            </Link>
            <div>
              {!investigation && step > 0 && (
                <Button
                  disabled={busy}
                  onClick={() =>
                    setStep(step === 4 && !PLANNING_ENABLED ? 2 : step - 1)
                  }
                >
                  Back
                </Button>
              )}
              <Button variant="primary" type="submit" disabled={busy}>
                {busy
                  ? "Saving…"
                  : investigation || step === 4
                    ? investigation
                      ? "Save changes"
                      : "Create investigation"
                    : step === 3 && !point
                      ? "Continue without confirmation"
                      : "Continue"}
              </Button>
            </div>
          </footer>
        </form>
      </div>
    </>
  );
}
export function InvestigationFormPage() {
  const { id } = useParams();
  const { token } = useSession();
  const resource = useResource(
    useCallback(
      async (signal) => {
        if (!id) return { investigation: null, location: null };
        const investigation = await getInvestigation(token, Number(id), signal);
        const location = PLANNING_ENABLED
          ? await getInvestigationLocation(token, Number(id))
          : null;
        return { investigation, location };
      },
      [token, id],
    ),
  );
  return resource.loading ? (
    <Skeleton rows={6} />
  ) : resource.error ? (
    <InlineAlert onRetry={resource.refresh}>{resource.error}</InlineAlert>
  ) : (
    <Editor
      key={id ?? "new"}
      investigation={resource.data?.investigation ?? null}
      existingPoint={resource.data?.location ?? null}
    />
  );
}
