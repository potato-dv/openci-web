import { useEffect, useState } from "react";

import { getReport, getReviews, reviewReport } from "../../services/api";
import type { Investigation, Report, Review } from "../../types/api";

type ReviewPanelProps = {
  token: string;
  investigation: Investigation;
  onChanged: () => void;
};

export function ReviewPanel({
  token,
  investigation,
  onChanged,
}: ReviewPanelProps) {
  const [report, setReport] = useState<Report | null>(null);
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
        const [reportData, reviewData] = await Promise.all([
          getReport(token, investigation.id),
          getReviews(token, investigation.id),
        ]);

        if (!cancelled) {
          setReport(reportData);
          setReviews(reviewData);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Could not load review data.",
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadReviewData();

    return () => {
      cancelled = true;
    };
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
      const review = await reviewReport(
        token,
        investigation.id,
        decision,
        comments.trim() || undefined,
      );
      setReviews((current) => [review, ...current]);
      setComments("");
      setMessage(
        decision === "approved"
          ? "Report approved and investigation completed."
          : "Report returned for correction.",
      );
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
          <h3>Supervisor review</h3>
          <p>Approve the submitted report or request corrections.</p>
        </div>
      </div>

      {!loading && !report && (
        <p className="empty-state">No report submitted yet.</p>
      )}
      {report && (
        <p className="workflow-meta">
          Report status: <strong>{report.status}</strong>
        </p>
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

      {error && <p className="error">{error}</p>}
      {message && <p className="success-message">{message}</p>}

      <div className="workflow-actions">
        <button
          type="button"
          className="secondary-button"
          onClick={() => void handleReview("returned_for_correction")}
          disabled={loading || saving || report?.status !== "submitted"}
        >
          Return for correction
        </button>
        <button
          type="button"
          className="primary-button compact-button"
          onClick={() => void handleReview("approved")}
          disabled={loading || saving || report?.status !== "submitted"}
        >
          Approve report
        </button>
      </div>

      {reviews.length > 0 && (
        <div className="workflow-history">
          <h4>Review history</h4>
          <ul>
            {reviews.map((review) => (
              <li key={review.id}>
                {review.decision.replaceAll("_", " ")} by reviewer{" "}
                {review.reviewer_id}
                {review.comments ? `: ${review.comments}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
