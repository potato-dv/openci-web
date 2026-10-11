import { useEffect, useState } from "react";

import { getReport, saveReport, submitReport } from "../../services/api";
import type { Investigation, Report } from "../../types/api";

type ReportEditorProps = {
  token: string;
  investigation: Investigation;
  onChanged: () => void;
};

export function ReportEditor({
  token,
  investigation,
  onChanged,
}: ReportEditorProps) {
  const [report, setReport] = useState<Report | null>(null);
  const [content, setContent] = useState("");
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

        if (!cancelled) {
          setReport(reportData);
          setContent(reportData.content);
        }
      } catch (err) {
        if (!cancelled) {
          if (err instanceof Error && err.message === "Report not found") {
            setReport(null);
            setContent("");
          } else {
            setError(
              err instanceof Error ? err.message : "Could not load report.",
            );
          }
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadReport();

    return () => {
      cancelled = true;
    };
  }, [investigation.id, token]);

  async function handleSave() {
    setSaving(true);
    setError("");
    setMessage("");

    try {
      const savedReport = await saveReport(token, investigation.id, content);
      setReport(savedReport);
      setContent(savedReport.content);
      setMessage("Draft saved.");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save draft.");
    } finally {
      setSaving(false);
    }
  }

  async function handleSubmit() {
    setSaving(true);
    setError("");
    setMessage("");

    try {
      const submittedReport = await submitReport(token, investigation.id);
      setReport(submittedReport);
      setMessage("Report submitted for supervisor review.");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit report.");
    } finally {
      setSaving(false);
    }
  }

  const isSubmitted = report?.status === "submitted";

  return (
    <section className="workflow-panel">
      <div className="section-heading">
        <div>
          <h3>Investigation report</h3>
          <p>Record findings and submit them for supervisor review.</p>
        </div>
        {report && <span className="count-badge">{report.status}</span>}
      </div>

      <label htmlFor="report-content">Findings</label>
      <textarea
        id="report-content"
        className="report-editor"
        value={content}
        onChange={(event) => setContent(event.target.value)}
        placeholder="Describe the investigation findings..."
        maxLength={20_000}
        disabled={loading || saving || isSubmitted}
      />

      {error && <p className="error">{error}</p>}
      {message && <p className="success-message">{message}</p>}

      {!isSubmitted && (
        <div className="workflow-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={() => void handleSave()}
            disabled={loading || saving || !content.trim()}
          >
            {saving ? "Saving..." : "Save draft"}
          </button>
          <button
            type="button"
            className="primary-button compact-button"
            onClick={() => void handleSubmit()}
            disabled={loading || saving || !content.trim()}
          >
            Submit report
          </button>
        </div>
      )}
    </section>
  );
}
