import { useEffect, useRef, useState } from "react";

import {
  getReport,
  getReportVersions,
  getReviews,
  reviewReport,
} from "@/features/reports/api";
import { CheckCircle2, CircleAlert, CircleHelp, ClipboardCheck } from "lucide-react";
import type { Investigation, Report, Review } from "@/types/api";
import { formatUserName } from "@/utils/userName";
import { InlineAlert } from "@/components/ui/Primitives";

type ReviewPanelProps = {
  token: string;
  investigation: Investigation;
  onChanged: () => void;
};

function displayValue(value: string | null | undefined) {
  return value ? value.replaceAll("_", " ") : "—";
}

function ReportDetails({ report }: { report: Report }) {
  const visitOutcomeClass = (report.visit_outcome ?? "unknown").replaceAll(
    "_",
    "-",
  );

  return (
    <div className="reviewed-report">
      <div className={`report-visit-result is-${visitOutcomeClass}`}>
        <span className="report-visit-result-icon" aria-hidden="true">
          {report.visit_outcome === "visited" ? (
            <CheckCircle2 size={19} strokeWidth={2.1} />
          ) : report.visit_outcome ? (
            <CircleAlert size={19} strokeWidth={2.1} />
          ) : (
            <CircleHelp size={19} strokeWidth={2.1} />
          )}
        </span>
        <div>
          <span className="report-visit-result-label">Visit outcome</span>
          <strong>{displayValue(report.visit_outcome)}</strong>
        </div>
      </div>
      <dl className="report-detail-grid m-0 grid grid-cols-2 gap-4 bg-transparent p-0 max-[520px]:grid-cols-1">
        <div className="border-t border-openci-border pt-3">
          <dt className="text-xs text-openci-text-muted">Investigation outcome</dt>
          <dd className="m-0 mt-1 break-words text-[13px] text-openci-text capitalize">
            <span className={`report-fact-badge is-${(report.outcome ?? "unknown").replaceAll("_", "-")}`}>
              {displayValue(report.outcome)}
            </span>
          </dd>
        </div>
        <div className="border-t border-openci-border pt-3">
          <dt className="text-xs text-openci-text-muted">Occupancy</dt>
          <dd className="m-0 mt-1 break-words text-[13px] text-openci-text capitalize">
            <span className={`report-fact-badge is-${(report.occupancy_status ?? "unknown").replaceAll("_", "-")}`}>
              {displayValue(report.occupancy_status)}
            </span>
          </dd>
        </div>
        <div className="border-t border-openci-border pt-3">
          <dt className="text-xs text-openci-text-muted">Visited at</dt>
          <dd className="m-0 mt-1 break-words text-[13px] text-openci-text capitalize">
            {report.visited_at ? new Date(report.visited_at).toLocaleString() : "—"}
          </dd>
        </div>
        <div className="border-t border-openci-border pt-3">
          <dt className="text-xs text-openci-text-muted">Verified address</dt>
          <dd className="m-0 mt-1 break-words text-[13px] text-openci-text capitalize">
            {report.verified_address || "—"}
          </dd>
        </div>
        <div className="border-t border-openci-border pt-3">
          <dt className="text-xs text-openci-text-muted">Author</dt>
          <dd className="m-0 mt-1 break-words text-[13px] text-openci-text capitalize">
            {formatUserName(report.author_name)}
          </dd>
        </div>
      </dl>
      {report.property_condition && (
        <div className="report-copy mt-4 max-w-[72ch]">
          <h4 className="mb-2 text-[13px] font-semibold text-openci-text">Property condition</h4>
          <p className="m-0 break-words whitespace-pre-wrap text-[13px] leading-relaxed text-openci-text-muted">
            {report.property_condition}
          </p>
        </div>
      )}
      {report.interaction_notes && (
        <div className="report-copy mt-4 max-w-[72ch]">
          <h4 className="mb-2 text-[13px] font-semibold text-openci-text">Interaction notes</h4>
          <p className="m-0 break-words whitespace-pre-wrap text-[13px] leading-relaxed text-openci-text-muted">
            {report.interaction_notes}
          </p>
        </div>
      )}
      <section className="report-findings" aria-label="Agent findings">
        <div className="report-findings-heading">
          <span className="report-findings-icon" aria-hidden="true">
            <ClipboardCheck size={18} strokeWidth={2} />
          </span>
          <div>
            <h4>Agent findings</h4>
            <p>Detailed notes recorded during the field visit</p>
          </div>
        </div>
        <p className="report-findings-content">{report.content}</p>
      </section>
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
  const [refreshError, setRefreshError] = useState("");
  const [message, setMessage] = useState("");
  const lastFreshAtRef = useRef(0);
  const loadedRef = useRef(false);
  const retryLoadRef = useRef<() => void>(() => {});

  useEffect(() => {
    let cancelled = false;
    let inFlight = false;

    async function loadReviewData() {
      if (cancelled || inFlight) return;
      inFlight = true;
      if (!loadedRef.current) setLoading(true);
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
          setRefreshError("");
          loadedRef.current = true;
          lastFreshAtRef.current = Date.now();
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Could not load review data.";
          if (loadedRef.current) setRefreshError(message);
          else setError(message);
        }
      } finally {
        inFlight = false;
        if (!cancelled) setLoading(false);
      }
    }

    retryLoadRef.current = () => void loadReviewData();
    void loadReviewData();
    const refreshIfStale = () => {
      if (
        !cancelled &&
        document.visibilityState === "visible" &&
        Date.now() - lastFreshAtRef.current >= 30_000
      ) void loadReviewData();
    };
    window.addEventListener("focus", refreshIfStale);
    document.addEventListener("visibilitychange", refreshIfStale);
    window.addEventListener("online", refreshIfStale);
    return () => {
      cancelled = true;
      window.removeEventListener("focus", refreshIfStale);
      document.removeEventListener("visibilitychange", refreshIfStale);
      window.removeEventListener("online", refreshIfStale);
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
      const review = await reviewReport(token, investigation.id, decision, comments.trim() || undefined);
      const nextStatus = decision === "approved" ? "approved" : "returned_for_correction";
      setReviews((current) => [review, ...current]);
      setReport((current) => current ? { ...current, status: nextStatus } : current);
      setVersions((current) => current.map((item) => item.id === review.report_id ? { ...item, status: nextStatus } : item));
      setComments("");
      setMessage(decision === "approved" ? "Report approved and investigation completed." : "Report returned for correction.");
      lastFreshAtRef.current = Date.now();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not review report.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="workflow-panel investigation-report-panel">
      <div className="section-heading">
        <div>
          <div className="workflow-title">
            <span className="workflow-title-icon" aria-hidden="true">
              <ClipboardCheck size={17} strokeWidth={2} />
            </span>
            <div>
              <h3>Report review</h3>
              <p>Review submitted findings and request corrections when needed.</p>
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

      {refreshError && (
        <InlineAlert onRetry={() => retryLoadRef.current()}>
          {refreshError}
        </InlineAlert>
      )}
      {loading && !report && <p className="muted">Loading report and review history…</p>}
      {!loading && !report && <p className="empty-state">No report submitted yet.</p>}
      {investigation.active_no_contact_event && (
        <section className="report-copy mt-4 max-w-[72ch]" aria-label="Open no-contact attempt">
          <h4 className="mb-2 text-[13px] font-semibold text-openci-text">Open no-contact attempt</h4>
          <dl className="report-detail-grid m-0 grid grid-cols-2 gap-4 bg-transparent p-0 max-[520px]:grid-cols-1">
            <div>
              <dt className="text-xs text-openci-text-muted">Reason</dt>
              <dd className="m-0 mt-1 break-words text-[13px] text-openci-text capitalize">{investigation.active_no_contact_event.reason.replaceAll("_", " ")}</dd>
            </div>
            <div>
              <dt className="text-xs text-openci-text-muted">Attempt</dt>
              <dd className="m-0 mt-1 break-words text-[13px] text-openci-text capitalize">{investigation.active_no_contact_event.retry_number + 1}</dd>
            </div>
            <div>
              <dt className="text-xs text-openci-text-muted">State</dt>
              <dd className="m-0 mt-1 break-words text-[13px] text-openci-text capitalize">{investigation.active_no_contact_event.state.replaceAll("_", " ")}</dd>
            </div>
            <div>
              <dt className="text-xs text-openci-text-muted">Work date</dt>
              <dd className="m-0 mt-1 break-words text-[13px] text-openci-text capitalize">{investigation.active_no_contact_event.work_date}</dd>
            </div>
            <div>
              <dt className="text-xs text-openci-text-muted">Attempted at</dt>
              <dd className="m-0 mt-1 break-words text-[13px] text-openci-text capitalize">
                {new Intl.DateTimeFormat("en-PH", {
                  dateStyle: "medium",
                  timeStyle: "short",
                  timeZone: "Asia/Manila",
                }).format(new Date(investigation.active_no_contact_event.attempted_at))}
              </dd>
            </div>
          </dl>
          {investigation.active_no_contact_event.notes && (
            <p className="m-0 break-words whitespace-pre-wrap text-[13px] leading-relaxed text-openci-text-muted">
              {investigation.active_no_contact_event.notes}
            </p>
          )}
        </section>
      )}
      {report && <ReportDetails report={report} />}

      {versions.length > 1 && (
        <div className="workflow-history report-version-history">
          <h4>Report versions</h4>
          <div className="report-version-list grid gap-1.5">
            {versions.map((version) => (
              <details key={version.id} className="report-version-item rounded-md border border-openci-border px-2.5 py-2">
                <summary className="cursor-pointer text-xs text-openci-text-muted open:mb-2 open:text-openci-text open:font-medium">Version {version.version} · {version.status.replaceAll("_", " ")} · {formatUserName(version.author_name)}</summary>
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
