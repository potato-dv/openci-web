import { useCallback, useMemo, useState, type FormEvent } from "react";
import type {
  AgentWorkProfile,
  LocationOption,
  WeeklySchedule,
  WeeklyScheduleDay,
} from "@/types/api";
import {
  getAgentAvailability,
  getAgentWeeklySchedule,
  getAgentWorkProfile,
  saveAgentWeeklySchedule,
  saveAgentWorkProfile,
} from "@/features/agents/api";
import { useResource } from "@/hooks/useResource";
import {
  LocationPicker,
  type ConfirmedPoint,
} from "@/components/map/LocationPicker";
import {
  Button,
  Checkbox,
  EmptyState,
  FormField,
  InlineAlert,
  Skeleton,
} from "@/components/ui/Primitives";

const weekdayNames = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

function previewEnd(date: string) {
  const end = new Date(`${date}T12:00:00Z`);
  end.setUTCDate(end.getUTCDate() + 30);
  return end.toISOString().slice(0, 10);
}

function defaultWeek(): WeeklyScheduleDay[] {
  return weekdayNames.map((_, weekday) => ({
    weekday,
    is_working: weekday < 5,
    shift_start: weekday < 5 ? "08:00" : null,
    shift_end: weekday < 5 ? "17:00" : null,
    break_start: weekday < 5 ? "12:00" : null,
    break_end: weekday < 5 ? "13:00" : null,
  }));
}

type WeeklyScheduleDraft = Pick<
  WeeklySchedule,
  | "region_code"
  | "enabled"
  | "effective_from"
  | "max_visits"
  | "max_open_cases"
  | "days"
>;

type WorkProfileDraft = {
  depot: ConfirmedPoint | null;
  endPoint: ConfirmedPoint | null;
  endEnabled: boolean;
};

function scheduleDraftFrom(
  value: WeeklySchedule | null,
  date: string,
): WeeklyScheduleDraft {
  return value
    ? {
        region_code: value.region_code,
        enabled: value.enabled,
        effective_from: value.effective_from,
        max_visits: value.max_visits,
        max_open_cases: value.max_open_cases,
        days: value.days.map((day) => ({ ...day })),
      }
    : {
        region_code: "ALL",
        enabled: true,
        effective_from: date,
        max_visits: 8,
        max_open_cases: 20,
        days: defaultWeek(),
      };
}

function profileDraftFrom(value: AgentWorkProfile | null): WorkProfileDraft {
  const endPoint = pointFrom(value, "end");
  return {
    depot: pointFrom(value, "depot"),
    endPoint,
    endEnabled: Boolean(endPoint),
  };
}

function pointFrom(
  profile: AgentWorkProfile | null,
  prefix: "depot" | "end",
): ConfirmedPoint | null {
  const latitude = profile?.[`${prefix}_latitude`];
  const longitude = profile?.[`${prefix}_longitude`];
  if (latitude == null || longitude == null) return null;
  return {
    latitude,
    longitude,
    label: profile?.[`${prefix}_label`] ?? null,
    source:
      (profile?.[`${prefix}_source`] as "manual" | "nominatim" | null) ??
      "manual",
    provider_ref: profile?.[`${prefix}_provider_ref`] ?? null,
  };
}

function localTime(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Manila",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(value));
}

function localDate(value: string) {
  return new Intl.DateTimeFormat("en-PH", {
    timeZone: "Asia/Manila",
    weekday: "short",
    month: "short",
    day: "numeric",
  }).format(new Date(`${value}T12:00:00+08:00`));
}

export function AgentWeeklyScheduleEditor({
  token,
  agentId,
  date,
  regions,
  onDirty,
  onUpdated,
}: {
  token: string;
  agentId: number;
  date: string;
  regions: LocationOption[];
  onDirty: (dirty: boolean) => void;
  onUpdated: () => void;
}) {
  const endDate = useMemo(() => previewEnd(date), [date]);
  const profile = useResource(
    useCallback(
      (signal) => getAgentWorkProfile(token, agentId, signal),
      [token, agentId],
    ),
  );
  const schedule = useResource(
    useCallback(
      (signal) => getAgentWeeklySchedule(token, agentId, date, signal),
      [token, agentId, date],
    ),
  );
  const availability = useResource(
    useCallback(
      (signal) => getAgentAvailability(token, agentId, date, endDate, signal),
      [token, agentId, date, endDate],
    ),
  );
  const [scheduleDraft, setScheduleDraft] =
    useState<WeeklyScheduleDraft | null>(null);
  const [profileDraft, setProfileDraft] = useState<WorkProfileDraft | null>(
    null,
  );
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const scheduleValues =
    scheduleDraft ?? scheduleDraftFrom(schedule.data, date);
  const {
    region_code: region,
    enabled,
    effective_from: effectiveFrom,
    max_visits: maxVisits,
    max_open_cases: maxOpenCases,
    days,
  } = scheduleValues;
  const profileValues = profileDraft ?? profileDraftFrom(profile.data);
  const { depot, endPoint, endEnabled } = profileValues;

  function updateScheduleDraft(update: Partial<WeeklyScheduleDraft>) {
    setScheduleDraft((current) => ({
      ...(current ?? scheduleDraftFrom(schedule.data, date)),
      ...update,
    }));
  }

  function updateProfileDraft(update: Partial<WorkProfileDraft>) {
    setProfileDraft((current) => ({
      ...(current ?? profileDraftFrom(profile.data)),
      ...update,
    }));
  }

  async function saveDepot(event: FormEvent) {
    event.preventDefault();
    if (!depot || (endEnabled && !endPoint)) {
      setError("Confirm the depot and any enabled ending point before saving.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await saveAgentWorkProfile(token, agentId, {
        depot_latitude: depot.latitude,
        depot_longitude: depot.longitude,
        depot_label: depot.label ?? null,
        depot_source: depot.source,
        depot_provider_ref: depot.provider_ref,
        end_latitude: endEnabled ? (endPoint?.latitude ?? null) : null,
        end_longitude: endEnabled ? (endPoint?.longitude ?? null) : null,
        end_label: endEnabled ? (endPoint?.label ?? null) : null,
        end_source: endEnabled ? (endPoint?.source ?? null) : null,
        end_provider_ref: endEnabled ? (endPoint?.provider_ref ?? null) : null,
      });
      setProfileDraft(profileDraftFrom(result));
      profile.refresh();
      availability.refresh();
      onUpdated();
      onDirty(false);
      setNotice(
        "Depot saved. It will be copied to the next recurring shift snapshot.",
      );
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? saveError.message
          : "Could not save the depot.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function saveSchedule(event: FormEvent) {
    event.preventDefault();
    if (!depot) {
      setError("Save a confirmed depot before enabling a recurring schedule.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await saveAgentWeeklySchedule(token, agentId, {
        effective_from: effectiveFrom,
        enabled,
        region_code: region,
        max_visits: maxVisits,
        max_open_cases: maxOpenCases,
        days,
      });
      setScheduleDraft({ ...scheduleValues, days: result.days });
      schedule.refresh();
      availability.refresh();
      onUpdated();
      onDirty(false);
      setNotice(
        "Weekly schedule saved. Daily shifts are created for today only.",
      );
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? saveError.message
          : "Could not save the weekly schedule.",
      );
    } finally {
      setBusy(false);
    }
  }

  function updateDay(index: number, values: Partial<WeeklyScheduleDay>) {
    const next = days.map((day, itemIndex) =>
      itemIndex === index ? { ...day, ...values } : day,
    );
    if (values.is_working === false) {
      next[index] = {
        ...next[index],
        shift_start: null,
        shift_end: null,
        break_start: null,
        break_end: null,
      };
    }
    if (values.is_working === true && !next[index].shift_start) {
      next[index] = {
        ...next[index],
        shift_start: "08:00",
        shift_end: "17:00",
      };
    }
    updateScheduleDraft({ days: next });
    onDirty(true);
  }

  return (
    <div className="agent-schedule-editor">
      <section className="schedule-section">
        <div className="schedule-section-heading">
          <div>
            <h3>Work profile</h3>
            <p>The depot is the default starting point for each new workday.</p>
          </div>
          {profile.loading && <span className="form-hint">Loading…</span>}
        </div>
        {profile.error && (
          <InlineAlert onRetry={profile.refresh}>{profile.error}</InlineAlert>
        )}
        <form
          className="shift-editor"
          onSubmit={saveDepot}
          onChange={() => onDirty(true)}
        >
          <h4>Configured depot</h4>
          <LocationPicker
            key={`depot-${profile.data?.updated_at ?? "unset"}`}
            token={token}
            initial={pointFrom(profile.data, "depot")}
            onConfirm={(value) => {
              updateProfileDraft({ depot: value });
              onDirty(true);
            }}
            onDirty={() => {
              updateProfileDraft({ depot: null });
              onDirty(true);
            }}
          />
          <Checkbox
            checked={endEnabled}
            onChange={(event) => {
              updateProfileDraft({ endEnabled: event.target.checked });
              onDirty(true);
            }}
          >
            Use a separate ending point
          </Checkbox>
          {endEnabled && (
            <LocationPicker
              key={`end-${profile.data?.updated_at ?? "unset"}`}
              token={token}
              initial={pointFrom(profile.data, "end")}
              onConfirm={(value) => {
                updateProfileDraft({ endPoint: value });
                onDirty(true);
              }}
              onDirty={() => {
                updateProfileDraft({ endPoint: null });
                onDirty(true);
              }}
            />
          )}
          <div className="form-footer">
            <Button
              variant="primary"
              type="submit"
              disabled={busy || profile.loading}
            >
              {busy ? "Saving…" : "Save depot"}
            </Button>
          </div>
        </form>
      </section>

      <section className="schedule-section">
        <div className="schedule-section-heading">
          <div>
            <h3>Weekly schedule</h3>
            <p>
              Repeats each week from its effective date. Dates use Philippine
              time.
            </p>
          </div>
          {schedule.loading && <span className="form-hint">Loading…</span>}
        </div>
        {schedule.error && (
          <InlineAlert onRetry={schedule.refresh}>{schedule.error}</InlineAlert>
        )}
        <form
          className="shift-editor"
          onSubmit={saveSchedule}
          onChange={() => onDirty(true)}
        >
          <div className="form-grid">
            <label>
              Service region
              <select
                value={region}
                onChange={(event) => {
                  updateScheduleDraft({ region_code: event.target.value });
                  onDirty(true);
                }}
              >
                <option value="ALL">All regions</option>
                {regions.map((item) => (
                  <option value={item.code} key={item.code}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <FormField
              label="Effective from"
              type="date"
              value={effectiveFrom}
              required
              onChange={(event) => {
                updateScheduleDraft({ effective_from: event.target.value });
                onDirty(true);
              }}
            />
            <FormField
              label="Maximum visits per day"
              type="number"
              min={1}
              max={50}
              value={maxVisits}
              required
              onChange={(event) => {
                updateScheduleDraft({ max_visits: Number(event.target.value) });
                onDirty(true);
              }}
            />
            <FormField
              label="Maximum open cases"
              type="number"
              min={1}
              max={200}
              value={maxOpenCases}
              required
              onChange={(event) => {
                updateScheduleDraft({
                  max_open_cases: Number(event.target.value),
                });
                onDirty(true);
              }}
            />
          </div>
          <Checkbox
            checked={enabled}
            onChange={(event) => {
              updateScheduleDraft({ enabled: event.target.checked });
              onDirty(true);
            }}
          >
            Weekly schedule enabled
          </Checkbox>
          <div className="schedule-days" aria-label="Weekly work days">
            {days.map((day, index) => (
              <fieldset className="schedule-day" key={day.weekday}>
                <legend>{weekdayNames[day.weekday]}</legend>
                <Checkbox
                  checked={day.is_working}
                  onChange={(event) =>
                    updateDay(index, { is_working: event.target.checked })
                  }
                >
                  Working day
                </Checkbox>
                {day.is_working && (
                  <>
                    <FormField
                      label="Starts"
                      type="time"
                      value={day.shift_start ?? "08:00"}
                      required
                      onChange={(event) =>
                        updateDay(index, { shift_start: event.target.value })
                      }
                    />
                    <FormField
                      label="Ends"
                      type="time"
                      value={day.shift_end ?? "17:00"}
                      required
                      onChange={(event) =>
                        updateDay(index, { shift_end: event.target.value })
                      }
                    />
                    <div className="schedule-break-fields">
                      <FormField
                        label="Break starts"
                        type="time"
                        value={day.break_start ?? ""}
                        onChange={(event) =>
                          updateDay(index, {
                            break_start: event.target.value || null,
                            break_end: event.target.value
                              ? (day.break_end ?? "13:00")
                              : null,
                          })
                        }
                      />
                      <FormField
                        label="Break ends"
                        type="time"
                        value={day.break_end ?? ""}
                        onChange={(event) =>
                          updateDay(index, {
                            break_end: event.target.value || null,
                            break_start: event.target.value
                              ? (day.break_start ?? "12:00")
                              : null,
                          })
                        }
                      />
                    </div>
                  </>
                )}
              </fieldset>
            ))}
          </div>
          <p className="form-hint">
            A fixed break is protected time. Visits cannot overlap it. Overnight
            shifts are not supported.
          </p>
          {error && <InlineAlert>{error}</InlineAlert>}
          {notice && <InlineAlert variant="success">{notice}</InlineAlert>}
          <div className="form-footer">
            <Button
              variant="primary"
              type="submit"
              disabled={busy || schedule.loading || profile.loading || !depot}
            >
              {busy ? "Saving…" : "Save weekly schedule"}
            </Button>
          </div>
        </form>
      </section>

      <section className="schedule-section">
        <div className="schedule-section-heading">
          <div>
            <h3>Next 31 days</h3>
            <p>
              Preview only. Future dated shifts are not created until their
              Manila workday.
            </p>
          </div>
          {availability.loading && <span className="form-hint">Loading…</span>}
        </div>
        {availability.error ? (
          <InlineAlert onRetry={availability.refresh}>
            {availability.error}
          </InlineAlert>
        ) : availability.data ? (
          <ul
            className="availability-preview"
            aria-label="31-day agent availability"
          >
            {availability.data.days.map((day) => (
              <li key={day.work_date}>
                <time dateTime={day.work_date}>{localDate(day.work_date)}</time>
                <span
                  className={`availability-state availability-${day.status}`}
                >
                  {day.status === "manual_override"
                    ? "Manual override"
                    : day.status === "scheduled"
                      ? "Scheduled"
                      : day.status === "shift_ended"
                        ? "Shift ended"
                        : day.status === "day_off"
                          ? "Day off"
                          : "Not configured"}
                </span>
                {day.shift_starts_at && day.shift_ends_at && (
                  <span className="availability-hours">
                    {localTime(day.shift_starts_at)}–
                    {localTime(day.shift_ends_at)}
                    {day.break_starts_at && day.break_ends_at
                      ? ` · break ${localTime(day.break_starts_at)}–${localTime(day.break_ends_at)}`
                      : ""}
                  </span>
                )}
              </li>
            ))}
          </ul>
        ) : availability.loading ? (
          <Skeleton rows={5} />
        ) : (
          <EmptyState title="No availability to preview">
            Set a depot and weekly schedule to see upcoming workdays.
          </EmptyState>
        )}
      </section>
    </div>
  );
}
