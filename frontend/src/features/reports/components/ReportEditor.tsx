import { useEffect, useState } from "react";
import { FilePenLine } from "lucide-react";

import {
  finalizeNoContactReport,
  getReport,
  getReportVersions,
  getRevisitRequest,
  requestRevisit,
  startInvestigation,
  saveReport,
  submitReport,
  unableToProceed,
} from "@/features/reports/api";
import { getAgentRoute } from "@/features/route-planning/api";
import type {
  Investigation,
  InvestigationOutcome,
  OccupancyStatus,
  Report,
  ReportInput,
  AgentRoute,
  RevisitRequest,
  VisitOutcome,
} from "@/types/api";
import { formatUserName } from "@/utils/userName";
import { PLANNING_ENABLED } from "@/config";
import { manilaToday } from "@/utils/format";

type ReportEditorProps = {
  token: string;
  investigation: Investigation;
  onChanged: () => void;
};

const emptyReport: ReportInput = {
  content: "",
  visit_outcome: null,
  outcome: null,
  verified_address: null,
  occupancy_status: null,
  property_condition: null,
  interaction_notes: null,
  visited_at: null,
};

function toLocalDateTime(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Manila",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? "00";
  return `${part("year")}-${part("month")}-${part("day")}T${part("hour")}:${part("minute")}`;
}

function toPayload(report: ReportInput): ReportInput {
  return {
    ...report,
    content: report.content,
    verified_address: report.verified_address?.trim() || null,
    property_condition: report.property_condition?.trim() || null,
    interaction_notes: report.interaction_notes?.trim() || null,
    visited_at: report.visited_at
      ? new Date(`${report.visited_at}:00+08:00`).toISOString()
      : null,
  };
}

export function ReportEditor({ token, investigation, onChanged }: ReportEditorProps) {
  const workDate = manilaToday();
  const [report, setReport] = useState<Report | null>(null);
  const [versions, setVersions] = useState<Report[]>([]);
  const [agentRoute, setAgentRoute] = useState<AgentRoute | null>(null);
  const [revisitRequest, setRevisitRequest] = useState<RevisitRequest | null>(null);
  const [form, setForm] = useState<ReportInput>(emptyReport);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [attemptReason, setAttemptReason] = useState<"no_contact_person" | "nobody_at_location" | "requested_later_visit" | "other">("no_contact_person");
  const [attemptNotes, setAttemptNotes] = useState("");
  const [contactFrom, setContactFrom] = useState("");
  const [contactUntil, setContactUntil] = useState("");
  const revisitRequestStatus = revisitRequest?.status;
  const routeStop = agentRoute?.stops.find((stop) => stop.investigation_id === investigation.id);
  const routeRevision = agentRoute?.route_revision ?? null;
  const routeAction = routeRevision == null
    ? null
    : { work_date: agentRoute?.work_date ?? workDate, route_revision: routeRevision };
  const isCurrentStop = Boolean(
    routeStop?.actionable && agentRoute?.current_actionable_investigation_id === investigation.id,
  );
  const canStart = Boolean(isCurrentStop && routeStop?.can_start && !routeStop.can_report);
  const canEdit = Boolean(isCurrentStop && routeStop?.can_report && routeAction);

  async function refreshRoute() {
    const latest = await getAgentRoute(token, workDate);
    setAgentRoute(latest);
    return latest;
  }

  useEffect(() => {
    let cancelled = false;

    async function loadReport() {
      setLoading(true);
      setError("");
      setMessage("");
      try {
        const [reportData, reportVersions, revisitData, routeData] = await Promise.all([
          getReport(token, investigation.id),
          getReportVersions(token, investigation.id),
          PLANNING_ENABLED
            ? getRevisitRequest(token, investigation.id)
            : Promise.resolve(null),
          PLANNING_ENABLED
            ? getAgentRoute(token, workDate).catch(() => null)
            : Promise.resolve(null),
        ]);
        if (cancelled) return;
        setReport(reportData);
        setVersions(reportVersions);
        setRevisitRequest(revisitData);
        setAgentRoute(routeData);
        setForm(reportData ? {
          content: reportData.content,
          visit_outcome: reportData.visit_outcome,
          outcome: reportData.outcome,
          verified_address: reportData.verified_address,
          occupancy_status: reportData.occupancy_status,
          property_condition: reportData.property_condition,
          interaction_notes: reportData.interaction_notes,
          visited_at: toLocalDateTime(reportData.visited_at),
        } : emptyReport);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof Error && err.message === "Report not found") {
          setReport(null);
          setVersions([]);
          setForm(emptyReport);
        } else {
          setError(err instanceof Error ? err.message : "Could not load report.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadReport();
    return () => { cancelled = true; };
  }, [investigation.id, investigation.status, token, workDate]);

  useEffect(() => {
    if (!PLANNING_ENABLED) return;
    let cancelled = false;
    const refresh = async () => {
      try {
        const latest = await getAgentRoute(token, workDate);
        if (!cancelled) setAgentRoute(latest);
      } catch {
        // Keep the last route snapshot; mutations are checked by the backend.
      }
    };
    const timer = window.setInterval(() => void refresh(), 10_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [token, workDate]);

  useEffect(() => {
    if (
      !PLANNING_ENABLED ||
      !revisitRequestStatus ||
      !["waiting_for_shift", "queued"].includes(revisitRequestStatus)
    ) {
      return;
    }
    let cancelled = false;
    const refreshStatus = async () => {
      try {
        const latest = await getRevisitRequest(token, investigation.id);
        if (!cancelled && latest) setRevisitRequest(latest);
      } catch {
        // Keep the last known request state; the next poll can recover.
      }
    };
    const intervalId = window.setInterval(() => void refreshStatus(), 15_000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [investigation.id, revisitRequestStatus, token]);

  function update<K extends keyof ReportInput>(key: K, value: ReportInput[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function handleSave() {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      if (!routeAction) throw new Error("Refresh your route before saving this report.");
      const saved = await saveReport(token, investigation.id, toPayload(form), routeAction);
      setReport(saved);
      setVersions((current) => [
        ...current.filter((item) => item.id !== saved.id),
        saved,
      ].sort((left, right) => left.version - right.version));
      setForm((current) => ({ ...current, visited_at: toLocalDateTime(saved.visited_at) }));
      setMessage(`Version ${saved.version} draft saved.`);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save draft.");
    } finally {
      setSaving(false);
    }
  }

  async function handleSubmit() {
    setError("");
    if (!form.visit_outcome) {
      setError("Select a visit outcome before submitting the report.");
      return;
    }
    if (!form.outcome) {
      setError("Select an investigation outcome before submitting the report.");
      return;
    }
    if (["visited", "no_access"].includes(form.visit_outcome) && !form.visited_at) {
      setError("Enter the date and time of the visit before submitting.");
      return;
    }
    if (form.outcome === "verified" && !form.verified_address?.trim()) {
      setError("Enter the verified address before submitting.");
      return;
    }
    if (!form.content.trim()) {
      setError("Enter detailed findings before submitting.");
      return;
    }

    setSaving(true);
    setMessage("");
    try {
      if (!routeAction) throw new Error("Refresh your route before submitting this report.");
      const saved = await saveReport(token, investigation.id, toPayload(form), routeAction);
      setReport(saved);
      const submitted = await submitReport(token, investigation.id, routeAction);
      setReport(submitted);
      setVersions((current) => [
        ...current.filter((item) => item.id !== submitted.id),
        submitted,
      ].sort((left, right) => left.version - right.version));
      setRevisitRequest((current) =>
        current && current.report_id !== submitted.id
          ? { ...current, status: "completed", completed_at: submitted.submitted_at }
          : current,
      );
      setMessage(`Version ${submitted.version} submitted for supervisor review.`);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit report.");
    } finally {
      setSaving(false);
    }
  }

  async function handleStart() {
    if (!routeAction) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await startInvestigation(token, investigation.id, routeAction);
      await refreshRoute();
      setMessage(routeStop?.sequence_state === "deferred_retry"
        ? "Retry started. Complete this visit before continuing the route."
        : "Investigation started. Complete this stop before continuing the route.");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start this investigation.");
    } finally {
      setSaving(false);
    }
  }

  function localToIso(value: string) {
    return value ? new Date(`${value}:00+08:00`).toISOString() : null;
  }

  async function handleUnableToProceed() {
    if (!routeAction) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await unableToProceed(token, investigation.id, {
        ...routeAction,
        reason: attemptReason,
        notes: attemptNotes.trim() || null,
        contact_available_from: localToIso(contactFrom),
        contact_available_until: localToIso(contactUntil),
      });
      setAttemptNotes("");
      setContactFrom("");
      setContactUntil("");
      await refreshRoute();
      setMessage("The no-contact attempt is recorded. The next route stop is now available.");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not record the no-contact attempt.");
    } finally {
      setSaving(false);
    }
  }

  async function handleFinalizeNoContact() {
    if (!routeAction || !routeStop?.active_attempt_id) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const finalized = await finalizeNoContactReport(
        token, investigation.id, routeStop.active_attempt_id, routeAction,
      );
      await refreshRoute();
      setMessage(finalized.next_work_date
        ? `No Contact Report saved. This investigation continues on ${finalized.next_work_date}.`
        : "No Contact Report saved. The attempt remains open for the next available shift.");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not finalize this no-contact attempt.");
    } finally {
      setSaving(false);
    }
  }

  async function handleRequestRevisit() {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const requested = await requestRevisit(token, investigation.id);
      setRevisitRequest(requested);
      setMessage(
        requested.target_work_date
          ? `Revisit route requested for ${requested.target_work_date}.`
          : "Revisit requested. It will be routed when your next available shift is configured.",
      );
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not request a revisit route.");
    } finally {
      setSaving(false);
    }
  }

  const locked = report?.status === "submitted" || report?.status === "approved";
  const reportFieldsDisabled = loading || saving || locked || !canEdit;
  const isReturned = report?.status === "returned_for_correction" || investigation.status === "returned_for_correction";
  const latestReturnedReport = [...versions]
    .filter((item) => item.status === "returned_for_correction")
    .sort((left, right) => right.version - left.version)[0];
  const requestMatchesReturnedReport = Boolean(
    latestReturnedReport && revisitRequest?.report_id === latestReturnedReport.id,
  );
  const hasActiveRevisitRequest = requestMatchesReturnedReport && [
    "waiting_for_shift", "queued", "routed",
  ].includes(revisitRequest?.status ?? "");
  const waitingForRevisitRoute = requestMatchesReturnedReport && [
    "waiting_for_shift", "queued",
  ].includes(revisitRequest?.status ?? "");
  const correctionIsOpen =
    investigation.status === "returned_for_correction" ||
    investigation.status === "in_progress";
  const canRequestRevisit = Boolean(
    PLANNING_ENABLED &&
      correctionIsOpen &&
      latestReturnedReport &&
      (!requestMatchesReturnedReport || !hasActiveRevisitRequest),
  );

  return (
    <section className="workflow-panel investigation-report-panel">
      <div className="section-heading">
        <div>
          <div className="workflow-title">
            <span className="workflow-title-icon" aria-hidden="true">
              <FilePenLine size={17} strokeWidth={2} />
            </span>
            <div>
              <h3>Investigation report</h3>
              <p>Record field visit details and findings for supervisor review.</p>
            </div>
          </div>
        </div>
        {report && (
          <span className="count-badge report-status-badge">
            Report · version {report.version} ·{" "}
            {report.status.replaceAll("_", " ")}
          </span>
        )}
      </div>

      {isReturned && <p className="workflow-meta">This version was returned. Saving your corrections creates a new version and keeps this one in the history.</p>}
      {!isReturned && canRequestRevisit && (
        <p className="workflow-meta">A previous report version was returned. Request a route to revisit this investigation when you are ready to address the concern.</p>
      )}
      {report?.author_name && <p className="workflow-meta">Report author: <strong>{formatUserName(report.author_name)}</strong></p>}

      {PLANNING_ENABLED && !routeRevision && (
        <p className="workflow-meta" role="status">
          The current route is not published yet. Refresh the route before starting or saving work.
        </p>
      )}
      {routeStop?.sequence_state === "upcoming" && (
        <p className="workflow-meta" role="status">
          This is an upcoming investigation. The current route stop must be completed or deferred first.
        </p>
      )}
      {routeStop?.priority_order_exception_reason && (
        <p className="workflow-meta" role="status">
          This stop has a published schedule exception because of its visit window, shift hours, or break.
        </p>
      )}
      {canStart && (
        <div className="workflow-actions">
          <button type="button" className="primary-button compact-button" onClick={() => void handleStart()} disabled={loading || saving}>
            {saving ? "Starting…" : routeStop?.sequence_state === "deferred_retry" ? "Retry Investigation" : "Start Current Investigation"}
          </button>
        </div>
      )}

      <div className="report-fields">
        <label>Visit outcome
          <select value={form.visit_outcome ?? ""} onChange={(event) => update("visit_outcome", (event.target.value || null) as VisitOutcome | null)} disabled={reportFieldsDisabled}>
            <option value="">Select visit outcome</option>
            <option value="visited">Visited</option>
            <option value="no_access">No access</option>
            <option value="unable_to_locate">Unable to locate</option>
          </select>
        </label>
        <label>Investigation outcome
          <select value={form.outcome ?? ""} onChange={(event) => update("outcome", (event.target.value || null) as InvestigationOutcome | null)} disabled={reportFieldsDisabled}>
            <option value="">Select investigation outcome</option>
            <option value="verified">Verified</option>
            <option value="not_verified">Not verified</option>
            <option value="unable_to_verify">Unable to verify</option>
            <option value="inconclusive">Inconclusive</option>
          </select>
        </label>
        <label>Verified address <span className="optional-label">Required when outcome is Verified</span>
          <input value={form.verified_address ?? ""} onChange={(event) => update("verified_address", event.target.value || null)} maxLength={500} disabled={reportFieldsDisabled} />
        </label>
        <label>Occupancy status <span className="optional-label">Optional</span>
          <select value={form.occupancy_status ?? ""} onChange={(event) => update("occupancy_status", (event.target.value || null) as OccupancyStatus | null)} disabled={reportFieldsDisabled}>
            <option value="">Select occupancy status</option>
            <option value="occupied">Occupied</option>
            <option value="vacant">Vacant</option>
            <option value="unknown">Unknown</option>
            <option value="not_applicable">Not applicable</option>
          </select>
        </label>
        <label>Visit date and time · Philippine time <span className="optional-label">Required for Visited or No access</span>
          <input type="datetime-local" value={form.visited_at ?? ""} onChange={(event) => update("visited_at", event.target.value || null)} disabled={reportFieldsDisabled} />
        </label>
      </div>

      <label htmlFor="property-condition">Property condition <span className="optional-label">Optional</span></label>
      <textarea id="property-condition" value={form.property_condition ?? ""} onChange={(event) => update("property_condition", event.target.value || null)} placeholder="Describe relevant property observations" disabled={reportFieldsDisabled} />

      <label htmlFor="interaction-notes">Interaction notes <span className="optional-label">Optional</span></label>
      <textarea id="interaction-notes" value={form.interaction_notes ?? ""} onChange={(event) => update("interaction_notes", event.target.value || null)} placeholder="Record factual notes about the interaction" disabled={reportFieldsDisabled} />

      <label className="report-findings-field-label" htmlFor="report-content">
        Detailed findings
        <span>Required · describe what you observed at the location</span>
      </label>
      <textarea
        id="report-content"
        className="report-editor report-findings-input"
        value={form.content}
        onChange={(event) => update("content", event.target.value)}
        placeholder="Describe the investigation findings..."
        maxLength={20_000}
        disabled={reportFieldsDisabled}
      />

      {canEdit && !locked && (
        <div className="report-fields">
          <label>Unable to proceed
            <select value={attemptReason} onChange={(event) => setAttemptReason(event.target.value as typeof attemptReason)} disabled={saving}>
              <option value="no_contact_person">No contact person available</option>
              <option value="nobody_at_location">Nobody at the location</option>
              <option value="requested_later_visit">Contact requested a later visit</option>
              <option value="other">Other</option>
            </select>
          </label>
          <label>Notes{attemptReason === "other" ? " · required" : " · optional"}
            <input value={attemptNotes} onChange={(event) => setAttemptNotes(event.target.value)} maxLength={4000} disabled={saving} />
          </label>
          <label>Contact available from · Philippine time
            <input type="datetime-local" value={contactFrom} onChange={(event) => setContactFrom(event.target.value)} disabled={saving} />
          </label>
          <label>Contact available until · Philippine time
            <input type="datetime-local" value={contactUntil} onChange={(event) => setContactUntil(event.target.value)} disabled={saving} />
          </label>
        </div>
      )}

      {loading && <p className="muted">Loading report…</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {message && <p className="success-message" role="status">{message}</p>}

      {canEdit && !locked && (
        <div className="workflow-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={() => void handleUnableToProceed()}
            disabled={saving || (attemptReason === "other" && !attemptNotes.trim())}
          >
            {saving ? "Recording attempt…" : "Unable to Proceed"}
          </button>
        </div>
      )}

      {routeStop?.sequence_state === "deferred" && routeStop.can_finalize_no_contact && routeStop.active_attempt_id != null && (
        <div className="workflow-actions">
          <button type="button" className="secondary-button" onClick={() => void handleFinalizeNoContact()} disabled={saving}>
            {saving ? "Saving…" : "Submit No Contact Report"}
          </button>
        </div>
      )}

      {requestMatchesReturnedReport && hasActiveRevisitRequest && revisitRequest && (
        <p className="workflow-meta" role="status">
          {revisitRequest.status === "waiting_for_shift"
            ? revisitRequest.target_work_date
              ? `Revisit requested for ${revisitRequest.target_work_date}; it will be routed when that shift begins. Submit after it is published and you complete the visit.`
              : "Revisit requested; waiting for your next available shift. Submit after the route is published and you complete the visit."
            : revisitRequest.status === "queued"
              ? `Revisit route update queued${revisitRequest.target_work_date ? ` for ${revisitRequest.target_work_date}` : ""}. Submit after the route is published and you complete the visit.`
              : `Revisit route published${revisitRequest.target_work_date ? ` for ${revisitRequest.target_work_date}` : ""}. Enter the return visit date and time before submitting.`}
        </p>
      )}

      {canRequestRevisit && (
        <div className="workflow-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={() => void handleRequestRevisit()}
            disabled={loading || saving}
          >
            {saving ? "Requesting route…" : "Continue correction · request revisit route"}
          </button>
        </div>
      )}

      {!locked && canEdit && (
        <div className="workflow-actions">
          <button type="button" className="secondary-button" onClick={() => void handleSave()} disabled={loading || saving || !form.content.trim()}>
            {saving ? "Saving…" : "Save draft"}
          </button>
          <button type="button" className="primary-button compact-button" onClick={() => void handleSubmit()} disabled={loading || saving || !form.content.trim() || waitingForRevisitRoute}>
            {saving ? "Submitting…" : "Submit report"}
          </button>
        </div>
      )}
    </section>
  );
}
