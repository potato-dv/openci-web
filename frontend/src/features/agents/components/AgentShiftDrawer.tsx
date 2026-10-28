import { useCallback, useRef, useState, type FormEvent } from "react";
import type {
  AgentRosterRow,
  AgentShiftInput,
  LocationOption,
} from "@/types/api";
import { getManagerAgentRoute, saveAgentShift } from "@/features/agents/api";
import { useResource } from "@/hooks/useResource";
import { LocationPicker, type ConfirmedPoint } from "@/components/map/LocationPicker";
import { AgentRouteView } from "./AgentRouteView";
import {
  Button,
  Checkbox,
  Drawer,
  FormField,
  InlineAlert,
  Skeleton,
  Tabs,
} from "@/components/ui/Primitives";
function localTime(value: string | undefined, fallback: string) {
  return value
    ? new Intl.DateTimeFormat("en-GB", {
        timeZone: "Asia/Manila",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
      }).format(new Date(value))
    : fallback;
}
export function AgentShiftDrawer({
  token,
  row,
  date,
  regions,
  onClose,
  onSaved,
}: {
  token: string;
  row: AgentRosterRow;
  date: string;
  regions: LocationOption[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const shift = row.shift;
  const [tab, setTab] = useState("shift");
  const [region, setRegion] = useState(
    shift?.region_code ?? regions[0]?.code ?? "",
  );
  const [available, setAvailable] = useState(shift?.is_available ?? true);
  const [startTime, setStartTime] = useState(
    localTime(shift?.shift_starts_at, "08:00"),
  );
  const [endTime, setEndTime] = useState(
    localTime(shift?.shift_ends_at, "17:00"),
  );
  const [visits, setVisits] = useState(shift?.max_visits ?? 8);
  const [open, setOpen] = useState(shift?.max_open_cases ?? 20);
  const [endEnabled, setEndEnabled] = useState(shift?.end_latitude != null);
  const [start, setStart] = useState<ConfirmedPoint | null>(
    shift
      ? {
          latitude: shift.start_latitude,
          longitude: shift.start_longitude,
          label: shift.start_location_label,
          source: shift.start_location_source ?? "manual",
          provider_ref: shift.start_location_provider_ref ?? null,
        }
      : null,
  );
  const [end, setEnd] = useState<ConfirmedPoint | null>(
    shift?.end_latitude != null && shift.end_longitude != null
      ? {
          latitude: shift.end_latitude,
          longitude: shift.end_longitude,
          label: shift.end_location_label,
          source: shift.end_location_source ?? "manual",
          provider_ref: shift.end_location_provider_ref ?? null,
        }
      : null,
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const lock = useRef(false);
  const route = useResource(
    useCallback(
      (signal) => getManagerAgentRoute(token, row.agent.id, date, signal),
      [token, row.agent.id, date],
    ),
  );
  function close() {
    if (!busy && (!dirty || window.confirm("Discard unsaved shift changes?")))
      onClose();
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!start || (endEnabled && !end)) {
      setError(
        "Confirm the starting point and any enabled ending point before saving.",
      );
      return;
    }
    if (endTime <= startTime) {
      setError("The shift must end after it starts on the selected date.");
      return;
    }
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    const payload: AgentShiftInput = {
      work_date: date,
      region_code: region,
      is_available: available,
      shift_starts_at: `${date}T${startTime}:00+08:00`,
      shift_ends_at: `${date}T${endTime}:00+08:00`,
      start_latitude: start.latitude,
      start_longitude: start.longitude,
      start_location_label: start.label,
      start_location_source: start.source,
      start_location_provider_ref: start.provider_ref,
      end_latitude: endEnabled ? end?.latitude : null,
      end_longitude: endEnabled ? end?.longitude : null,
      end_location_label: endEnabled ? end?.label : null,
      end_location_source: endEnabled ? end?.source : null,
      end_location_provider_ref: endEnabled ? end?.provider_ref : null,
      max_visits: visits,
      max_open_cases: open,
    };
    try {
      await saveAgentShift(token, row.agent.id, payload);
      setDirty(false);
      onSaved();
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Could not save the shift.",
      );
    } finally {
      setBusy(false);
      lock.current = false;
    }
  }
  return (
    <Drawer open title={row.agent.name} onClose={close}>
      <p className="form-hint">
        Account: {row.agent.is_active ? "Active" : "Inactive"} · Shift date:{" "}
        {date}
      </p>
      <Tabs
        value={tab}
        onChange={setTab}
        label="Agent details"
        items={[
          { value: "shift", label: "Shift" },
          { value: "work", label: "Assigned work" },
        ]}
      />
      {tab === "work" ? (
        route.loading ? (
          <Skeleton />
        ) : route.error ? (
          <InlineAlert onRetry={route.refresh}>{route.error}</InlineAlert>
        ) : (
          route.data && (
            <AgentRouteView
              data={route.data}
              agentId={row.agent.id}
              agentName={row.agent.name}
            />
          )
        )
      ) : (
        <form
          className="shift-editor"
          onSubmit={save}
          onChange={() => setDirty(true)}
        >
          <div className="form-grid">
            <label>
              Service region
              <select
                value={region}
                onChange={(event) => setRegion(event.target.value)}
                required
              >
                {regions.map((item) => (
                  <option value={item.code} key={item.code}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <Checkbox
              checked={available}
              onChange={(event) => setAvailable(event.target.checked)}
            >
              Available for assignments
            </Checkbox>
            <FormField
              label="Shift starts · Philippine time"
              type="time"
              required
              value={startTime}
              onChange={(event) => setStartTime(event.target.value)}
            />
            <FormField
              label="Shift ends · Philippine time"
              type="time"
              required
              value={endTime}
              onChange={(event) => setEndTime(event.target.value)}
            />
            <FormField
              label="Maximum visits"
              type="number"
              min={1}
              max={50}
              required
              value={visits}
              onChange={(event) => setVisits(Number(event.target.value))}
            />
            <FormField
              label="Maximum open cases"
              type="number"
              min={1}
              max={200}
              required
              value={open}
              onChange={(event) => setOpen(Number(event.target.value))}
            />
          </div>
          <h3>Configured starting point</h3>
          <LocationPicker
            token={token}
            initial={start}
            onConfirm={(value) => {
              setStart(value);
              setDirty(true);
            }}
            onDirty={() => {
              setStart(null);
              setDirty(true);
            }}
          />
          <Checkbox
            checked={endEnabled}
            onChange={(event) => setEndEnabled(event.target.checked)}
          >
            Set a separate ending point
          </Checkbox>
          {endEnabled && (
            <LocationPicker
              token={token}
              initial={end}
              onConfirm={(value) => {
                setEnd(value);
                setDirty(true);
              }}
              onDirty={() => {
                setEnd(null);
                setDirty(true);
              }}
            />
          )}
          {shift?.current_planning_run_id && (
            <InlineAlert variant="warning">
              Saving this shift will replace its published route. Routes for
              assigned work will be rebuilt automatically with the updated
              shift settings.
            </InlineAlert>
          )}
          {error && <InlineAlert>{error}</InlineAlert>}
          <div className="form-footer">
            <Button onClick={close} disabled={busy}>
              Cancel
            </Button>
            <Button
              variant="primary"
              type="submit"
              disabled={busy || !row.agent.is_active}
            >
              {busy ? "Saving…" : "Save shift"}
            </Button>
          </div>
        </form>
      )}
    </Drawer>
  );
}
