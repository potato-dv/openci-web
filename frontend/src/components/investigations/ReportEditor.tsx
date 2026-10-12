import { useEffect, useState } from "react";

import { getReport, saveReport, submitReport } from "../../services/api";
import type {
  Investigation,
  InvestigationOutcome,
  OccupancyStatus,
  Report,
  ReportInput,
  VisitOutcome,
} from "../../types/api";

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
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 16);
}

function toPayload(report: ReportInput): ReportInput {
  return {
    ...report,
    content: report.content,
    verified_address: report.verified_address?.trim() || null,
    property_condition: report.property_condition?.trim() || null,
    interaction_notes: report.interaction_notes?.trim() || null,
    visited_at: report.visited_at ? new Date(report.visited_at).toISOString() : null,
  };
}

export function ReportEditor({ token, investigation, onChanged }: ReportEditorProps) {
  const [report, setReport] = useState<Report | null>(null);
  const [form, setForm] = useState<ReportInput>(emptyReport);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadReport() {
      setLoading(true);
      setError("");
      setMessage("");
      try {
        const reportData = await getReport(token, investigation.id);
        if (cancelled) return;
        setReport(reportData);
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
  }, [investigation.id, token]);

  function update<K extends keyof ReportInput>(key: K, value: ReportInput[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function handleSave() {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const saved = await saveReport(token, investigation.id, toPayload(form));
      setReport(saved);
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
      const saved = await saveReport(token, investigation.id, toPayload(form));
      setReport(saved);
      const submitted = await submitReport(token, investigation.id);
      setReport(submitted);
      setMessage(`Version ${submitted.version} submitted for supervisor review.`);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit report.");
    } finally {
      setSaving(false);
    }
  }

  const locked = report?.status === "submitted" || report?.status === "approved";
  const isReturned = report?.status === "returned_for_correction" || investigation.status === "returned_for_correction";

  return (
    <section className="workflow-panel">
      <div className="section-heading">
        <div>
          <h3>Investigation report</h3>
          <p>Record field visit details and findings for supervisor review.</p>
        </div>
        {report && <span className="count-badge">Version {report.version} · {report.status.replaceAll("_", " ")}</span>}
      </div>

      {isReturned && <p className="workflow-meta">This version was returned. Saving your corrections creates a new version and keeps this one in the history.</p>}
      {report?.author_name && <p className="workflow-meta">Report author: <strong>{report.author_name}</strong></p>}

      <div className="report-fields">
        <label>Visit outcome
          <select value={form.visit_outcome ?? ""} onChange={(event) => update("visit_outcome", (event.target.value || null) as VisitOutcome | null)} disabled={loading || saving || locked}>
            <option value="">Select visit outcome</option>
            <option value="visited">Visited</option>
            <option value="no_access">No access</option>
            <option value="unable_to_locate">Unable to locate</option>
          </select>
        </label>
        <label>Investigation outcome
          <select value={form.outcome ?? ""} onChange={(event) => update("outcome", (event.target.value || null) as InvestigationOutcome | null)} disabled={loading || saving || locked}>
            <option value="">Select investigation outcome</option>
            <option value="verified">Verified</option>
            <option value="not_verified">Not verified</option>
            <option value="unable_to_verify">Unable to verify</option>
            <option value="inconclusive">Inconclusive</option>
          </select>
        </label>
        <label>Verified address <span className="optional-label">Required when outcome is Verified</span>
          <input value={form.verified_address ?? ""} onChange={(event) => update("verified_address", event.target.value || null)} maxLength={500} disabled={loading || saving || locked} />
        </label>
        <label>Occupancy status <span className="optional-label">Optional</span>
          <select value={form.occupancy_status ?? ""} onChange={(event) => update("occupancy_status", (event.target.value || null) as OccupancyStatus | null)} disabled={loading || saving || locked}>
            <option value="">Select occupancy status</option>
            <option value="occupied">Occupied</option>
            <option value="vacant">Vacant</option>
            <option value="unknown">Unknown</option>
            <option value="not_applicable">Not applicable</option>
          </select>
        </label>
        <label>Visit date and time <span className="optional-label">Required for Visited or No access</span>
          <input type="datetime-local" value={form.visited_at ?? ""} onChange={(event) => update("visited_at", event.target.value || null)} disabled={loading || saving || locked} />
        </label>
      </div>

      <label htmlFor="property-condition">Property condition <span className="optional-label">Optional</span></label>
      <textarea id="property-condition" value={form.property_condition ?? ""} onChange={(event) => update("property_condition", event.target.value || null)} placeholder="Describe relevant property observations" disabled={loading || saving || locked} />

      <label htmlFor="interaction-notes">Interaction notes <span className="optional-label">Optional</span></label>
      <textarea id="interaction-notes" value={form.interaction_notes ?? ""} onChange={(event) => update("interaction_notes", event.target.value || null)} placeholder="Record factual notes about the interaction" disabled={loading || saving || locked} />

      <label htmlFor="report-content">Detailed findings</label>
      <textarea
        id="report-content"
        className="report-editor"
        value={form.content}
        onChange={(event) => update("content", event.target.value)}
        placeholder="Describe the investigation findings..."
        maxLength={20_000}
        disabled={loading || saving || locked}
      />

      {loading && <p className="muted">Loading report…</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {message && <p className="success-message" role="status">{message}</p>}

      {!locked && (
        <div className="workflow-actions">
          <button type="button" className="secondary-button" onClick={() => void handleSave()} disabled={loading || saving || !form.content.trim()}>
            {saving ? "Saving…" : "Save draft"}
          </button>
          <button type="button" className="primary-button compact-button" onClick={() => void handleSubmit()} disabled={loading || saving || !form.content.trim()}>
            {saving ? "Submitting…" : "Submit report"}
          </button>
        </div>
      )}
    </section>
  );
}
