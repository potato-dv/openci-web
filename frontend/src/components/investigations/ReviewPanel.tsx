import { useEffect, useState } from "react";

import { getReport, getReportVersions, getReviews, reviewReport } from "../../services/api";
import type { Investigation, Report, Review } from "../../types/api";
import { formatUserName } from "../../utils/userName";

type ReviewPanelProps = {
  token: string;
  investigation: Investigation;
  onChanged: () => void;
};

function displayValue(value: string | null | undefined) {
  return value ? value.replaceAll("_", " ") : "—";
}

function ReportDetails({ report }: { report: Report }) {
  return (
    <div className="reviewed-report">
      <dl className="report-detail-grid">
        <div><dt>Visit outcome</dt><dd>{displayValue(report.visit_outcome)}</dd></div>
        <div><dt>Investigation outcome</dt><dd>{displayValue(report.outcome)}</dd></div>
        <div><dt>Occupancy</dt><dd>{displayValue(report.occupancy_status)}</dd></div>
        <div><dt>Visited at</dt><dd>{report.visited_at ? new Date(report.visited_at).toLocaleString() : "—"}</dd></div>
        <div><dt>Verified address</dt><dd>{report.verified_address || "—"}</dd></div>
        <div><dt>Author</dt><dd>{formatUserName(report.author_name)}</dd></div>
      </dl>
      {report.property_condition && <div className="report-copy"><h4>Property condition</h4><p>{report.property_condition}</p></div>}
      {report.interaction_notes && <div className="report-copy"><h4>Interaction notes</h4><p>{report.interaction_notes}</p></div>}
      <div className="report-copy"><h4>Detailed findings</h4><p>{report.content}</p></div>
    </div>
  );
}

export function ReviewPanel({ token, investigation, onChanged }: ReviewPanelProps) {
  const [report, setReport] = useState<Report | null>(null);
  const [versions, setVersions] = useState<Report[]>([]);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [comments, setComments] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadReviewData() {
      setLoading(true);
      setError("");
      try {
        const [reportData, versionData, reviewData] = await Promise.all([
          getReport(token, investigation.id),
          getReportVersions(token, investigation.id),
          getReviews(token, investigation.id),
        ]);
        if (!cancelled) {
          setReport(reportData);
          setVersions(versionData);
          setReviews(reviewData);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load review data.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadReviewData();
    return () => { cancelled = true; };
  }, [investigation.id, token]);

  async function handleReview(decision: Review["decision"]) {
    if (decision === "returned_for_correction" && !comments.trim()) {
      setError("Add correction comments before returning the report.");
      return;
    }

    setSaving(true);
    setError("");
    setMessage("");
    try {
      const review = await reviewReport(token, investigation.id, decision, comments.trim() || undefined);
      const nextStatus = decision === "approved" ? "approved" : "returned_for_correction";
      setReviews((current) => [review, ...current]);
      setReport((current) => current ? { ...current, status: nextStatus } : current);
      setVersions((current) => current.map((item) => item.id === review.report_id ? { ...item, status: nextStatus } : item));
      setComments("");
      setMessage(decision === "approved" ? "Report approved and investigation completed." : "Report returned for correction.");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not review report.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="workflow-panel">
      <div className="section-heading">
        <div>
          <h3>Report review</h3>
          <p>Review submitted findings and request corrections when needed.</p>
        </div>
        {report && <span className="count-badge">Version {report.version} · {report.status.replaceAll("_", " ")}</span>}
      </div>

      {loading && <p className="muted">Loading report and review history…</p>}
      {!loading && !report && <p className="empty-state">No report submitted yet.</p>}
      {report && <ReportDetails report={report} />}

      {versions.length > 1 && (
        <div className="workflow-history report-version-history">
          <h4>Report versions</h4>
          <div className="report-version-list">
            {versions.map((version) => (
              <details key={version.id} className="report-version-item">
                <summary>Version {version.version} · {version.status.replaceAll("_", " ")} · {formatUserName(version.author_name)}</summary>
                <ReportDetails report={version} />
              </details>
            ))}
          </div>
        </div>
      )}

      <label htmlFor="review-comments">Review comments</label>
      <textarea
        id="review-comments"
        className="review-comments"
        value={comments}
        onChange={(event) => setComments(event.target.value)}
        placeholder="Required when returning for correction"
        maxLength={5_000}
        disabled={loading || saving || report?.status !== "submitted"}
      />

      {error && <p className="error" role="alert">{error}</p>}
      {message && <p className="success-message" role="status">{message}</p>}

      <div className="workflow-actions">
        <button type="button" className="secondary-button" onClick={() => void handleReview("returned_for_correction")} disabled={loading || saving || report?.status !== "submitted"}>
          {saving ? "Saving…" : "Return for correction"}
        </button>
        <button type="button" className="primary-button compact-button" onClick={() => void handleReview("approved")} disabled={loading || saving || report?.status !== "submitted"}>
          {saving ? "Saving…" : "Approve report"}
        </button>
      </div>

      {reviews.length > 0 && (
        <div className="workflow-history">
          <h4>Review history</h4>
          <ul>
            {reviews.map((review) => (
              <li key={review.id}>
                {review.decision.replaceAll("_", " ")} by {formatUserName(review.reviewer_name)} · {new Date(review.reviewed_at).toLocaleString()}
                {review.comments ? `: ${review.comments}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
