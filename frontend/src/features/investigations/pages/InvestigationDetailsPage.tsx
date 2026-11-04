import { useRef, useState } from "react";
import { Link } from "react-router";
import { deleteInvestigation } from "@/features/investigations/api";
import type { Investigation, User } from "@/types/api";
import { AssignmentPanel } from "@/features/investigations/components/AssignmentPanel";
import { ReportEditor } from "@/features/reports/components/ReportEditor";
import { ReviewPanel } from "@/features/reports/components/ReviewPanel";
import { formatUserName } from "@/utils/userName";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { PriorityBadge } from "@/components/ui/PriorityBadge";
import { Modal } from "@/components/ui/Modal";
import { LocationConfirmationPanel } from "@/features/investigations/components/LocationConfirmationPanel";
import { PLANNING_ENABLED } from "@/config";
import { duration as formatDuration } from "@/utils/format";

type InvestigationDetailsPageProps = {
  token: string;
  user: User;
  investigation: Investigation;
  onChanged: () => void;
  onDeleted: (item: Investigation) => void;
};

export function InvestigationDetailsPage({
  token,
  user,
  investigation,
  onChanged,
  onDeleted,
}: InvestigationDetailsPageProps) {
  const canManage = user.role === "admin" || user.role === "supervisor";
  const hasVisitRequirements =
    investigation.service_duration_seconds != null ||
    investigation.visit_not_before_at != null ||
    investigation.visit_due_at != null;
  const [softDeleting, setSoftDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const deleteInFlight = useRef(false);
  const [deleteError, setDeleteError] = useState("");

  async function handleDelete() {
    if (deleteInFlight.current) return;
    deleteInFlight.current = true;
    setDeleteError("");
    setSoftDeleting(true);
    try {
      await deleteInvestigation(token, investigation.id);
      onDeleted(investigation);
    } catch (err) {
      setDeleteError(
        err instanceof Error
          ? err.message
          : "Could not move investigation to Trash.",
      );
    } finally {
      deleteInFlight.current = false;
      setSoftDeleting(false);
    }
  }

  return (
    <div
      className={`details-layout investigation-details ${
        canManage ? "investigation-manager-details" : "investigation-agent-details"
      }`}
    >
      <section className="details-summary investigation-overview">
        <div className="details-page-heading">
          <div className="details-page-identity">
            <h1 id="investigation-name">
              {formatUserName(investigation.subject_name)}
            </h1>
            <p className="details-reference">
              <span className="details-reference-label">Reference</span>
              {investigation.reference_number}
            </p>
          </div>
          <div className="details-page-controls">
            {canManage && (
              <div className="details-actions">
                <Link
                  className="secondary-button toolbar-button"
                  to={`/investigations/${investigation.id}/edit`}
                >
                  Edit investigation
                </Link>
                <button
                  className="danger-button toolbar-button"
                  type="button"
                  onClick={() => {
                    setDeleteError("");
                    setConfirmDelete(true);
                  }}
                >
                  Move to Trash
                </button>
              </div>
            )}
          </div>
        </div>
        <dl className="details-grid investigation-overview-grid">
          <div className="investigation-overview-address">
            <dt>Address</dt>
            <dd>{investigation.address_display}</dd>
          </div>
          <div>
            <dt>Investigation status</dt>
            <dd>
              <StatusBadge
                status={investigation.status}
                reopenOn={investigation.reopen_on}
              />
            </dd>
          </div>
          <div>
            <dt>Priority</dt>
            <dd>
              <PriorityBadge priority={investigation.priority} />
            </dd>
          </div>
          <div>
            <dt>Assigned agent</dt>
            <dd>
              {investigation.assigned_agent_name
                ? formatUserName(investigation.assigned_agent_name)
                : "Unassigned"}
            </dd>
          </div>
        </dl>
        {hasVisitRequirements && (
          <section
            className="visit-requirements"
            aria-labelledby="visit-requirements-title"
          >
            <div className="visit-requirements-heading">
              <div>
                <h2 id="visit-requirements-title">Visit requirements</h2>
                <p>All times use Philippine time (UTC+8).</p>
              </div>
            </div>
            <dl className="visit-requirements-grid">
              <div>
                <dt>Estimated visit duration</dt>
                <dd>
                  {investigation.service_duration_seconds != null
                    ? formatDuration(investigation.service_duration_seconds)
                    : "Not provided"}
                </dd>
              </div>
              <div>
                <dt>Earliest visit</dt>
                <dd>
                  {formatManilaDateTime(
                    investigation.visit_not_before_at,
                    "No earliest visit set",
                  )}
                </dd>
              </div>
              <div>
                <dt>Completion deadline</dt>
                <dd>
                  {formatManilaDateTime(
                    investigation.visit_due_at,
                    "No deadline set",
                  )}
                </dd>
              </div>
            </dl>
          </section>
        )}
      </section>

      {canManage && (
        <Modal
          open={confirmDelete}
          title="Move investigation to Trash"
          onClose={() => !softDeleting && setConfirmDelete(false)}
        >
          <div className="confirm-dialog-copy">
            <p>
              Move <strong>{investigation.reference_number}</strong> to Trash?
            </p>
            <p>
              The investigation and its history will be retained. An
              administrator can permanently delete it from Trash.
            </p>
            {deleteError && (
              <p className="error" role="alert">
                {deleteError}
              </p>
            )}
            <div className="modal-form-actions">
              <button
                type="button"
                className="secondary-button toolbar-button"
                onClick={() => setConfirmDelete(false)}
                disabled={softDeleting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="danger-button toolbar-button"
                onClick={() => void handleDelete()}
                disabled={softDeleting}
              >
                {softDeleting ? "Moving to Trash…" : "Move to Trash"}
              </button>
            </div>
          </div>
        </Modal>
      )}
      <div className="investigation-workspace-grid">
        {canManage && (
          <div className="investigation-workspace-column investigation-planning-column">
            {PLANNING_ENABLED && (
              <LocationConfirmationPanel
                token={token}
                investigation={investigation}
                onChanged={onChanged}
              />
            )}
            <div id="assignment">
              <AssignmentPanel
                token={token}
                investigation={investigation}
                onChanged={onChanged}
              />
            </div>
          </div>
        )}
        <div
          id="report"
          className="investigation-workspace-column investigation-report-column"
        >
          {user.role === "agent" && (
            <ReportEditor
              token={token}
              investigation={investigation}
              onChanged={onChanged}
            />
          )}

          {(user.role === "supervisor" || user.role === "admin") && (
            <ReviewPanel
              token={token}
              investigation={investigation}
              onChanged={onChanged}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function formatManilaDateTime(
  value: string | null | undefined,
  emptyLabel: string,
) {
  if (!value) return emptyLabel;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return emptyLabel;
  return new Intl.DateTimeFormat("en-PH", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Manila",
  }).format(parsed);
}
