import { useCallback, useRef, useState } from "react";
import { Link } from "react-router";
import { deleteInvestigation } from "@/features/investigations/api";
import type { AgentPermissions, Investigation, User } from "@/types/api";
import { InvestigationActivityTimeline } from "@/features/investigations/components/InvestigationActivityTimeline";
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
  agentPermissions?: AgentPermissions | null;
  investigation: Investigation;
  onChanged: () => void;
  onDeleted: (item: Investigation) => void;
};

const detailTermClassName =
  "text-xs font-semibold leading-[1.4] text-openci-text-muted";
const detailValueClassName =
  "mb-0 mt-1 break-words text-sm leading-[1.45] text-openci-text";

export function InvestigationDetailsPage({
  token,
  user,
  agentPermissions,
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
  const [activityRefreshKey, setActivityRefreshKey] = useState(0);
  const handleChanged = useCallback(() => {
    onChanged();
    setActivityRefreshKey((current) => current + 1);
  }, [onChanged]);

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
      className={`investigation-details mx-auto grid max-w-[1320px] min-w-0 gap-6 ${
        canManage ? "investigation-manager-details" : "investigation-agent-details"
      }`}
    >
      <section id="overview" className="details-summary investigation-overview relative overflow-hidden rounded-xl border border-[#dce4ef] bg-white p-6 shadow-[0_2px_12px_rgba(22,45,86,0.035)] max-[767px]:p-4">
        <div className="details-page-heading flex min-w-0 flex-wrap items-center justify-between gap-6 max-[767px]:items-start max-[767px]:gap-4 max-[520px]:flex-col max-[520px]:items-stretch">
          <div className="details-page-identity flex min-w-0 flex-col items-start">
            <h1 id="investigation-name" className="m-0 break-words text-[25px] font-semibold leading-[1.25] tracking-[-0.02em] text-openci-text max-[767px]:text-[22px]">
              {formatUserName(investigation.subject_name)}
            </h1>
            <p className="mt-2 inline-flex w-fit items-baseline gap-2 rounded-md bg-openci-surface-selected px-2 py-1 text-xs font-semibold tabular-nums text-openci-accent-strong">
              <span className="font-medium">Reference</span>
              {investigation.reference_number}
            </p>
          </div>
          <div className="details-page-controls flex shrink-0 flex-wrap items-center justify-end gap-[9px] max-[767px]:w-full max-[767px]:justify-start">
            {canManage && (
              <div className="details-actions flex flex-wrap gap-[7px] max-[767px]:w-full">
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
        <dl className="details-grid investigation-overview-grid mt-6 grid grid-cols-3 gap-x-6 gap-y-4 border-t border-openci-border pt-4 max-[900px]:grid-cols-2 max-[767px]:mt-4 max-[767px]:gap-x-4 max-[767px]:gap-y-3 max-[767px]:pt-4 max-[520px]:grid-cols-1">
          <div className="investigation-overview-address col-span-full min-w-0 rounded-lg bg-openci-surface-muted px-4 py-3 max-[767px]:pb-3 max-[520px]:col-auto">
            <dt className={detailTermClassName}>Address</dt>
            <dd className={detailValueClassName}>{investigation.address_display}</dd>
          </div>
          <div className="min-w-0">
            <dt className={detailTermClassName}>Investigation status</dt>
            <dd className={detailValueClassName}>
              <StatusBadge
                status={investigation.status}
                reopenOn={investigation.reopen_on}
              />
            </dd>
          </div>
          <div className="min-w-0">
            <dt className={detailTermClassName}>Priority</dt>
            <dd className={detailValueClassName}>
              <PriorityBadge priority={investigation.priority} />
            </dd>
          </div>
          <div className="min-w-0">
            <dt className={detailTermClassName}>Assigned agent</dt>
            <dd className={detailValueClassName}>
              {investigation.assigned_agent_name
                ? formatUserName(investigation.assigned_agent_name)
                : "Unassigned"}
            </dd>
          </div>
        </dl>
        {hasVisitRequirements && (
          <section
            className="mt-5 rounded-lg border border-openci-border bg-openci-surface-muted p-4"
            aria-labelledby="visit-requirements-title"
          >
            <div>
              <div>
                <h2
                  id="visit-requirements-title"
                  className="m-0 text-base font-semibold leading-[1.4] tracking-[-0.015em] text-openci-text"
                >
                  Visit requirements
                </h2>
                <p className="mb-0 mt-1 text-xs leading-[1.45] text-openci-text-muted">
                  All times use Philippine time (UTC+8).
                </p>
              </div>
            </div>
            <dl className="m-0 mt-4 grid grid-cols-3 gap-x-6 gap-y-4 p-0 max-[900px]:grid-cols-2 max-[767px]:gap-x-4 max-[767px]:gap-y-3 max-[520px]:grid-cols-1">
              <div className="min-w-0">
                <dt className={detailTermClassName}>Estimated visit duration</dt>
                <dd className={detailValueClassName}>
                  {investigation.service_duration_seconds != null
                    ? formatDuration(investigation.service_duration_seconds)
                    : "Not provided"}
                </dd>
              </div>
              <div className="min-w-0">
                <dt className={detailTermClassName}>Earliest visit</dt>
                <dd className={detailValueClassName}>
                  {formatManilaDateTime(
                    investigation.visit_not_before_at,
                    "No earliest visit set",
                  )}
                </dd>
              </div>
              <div className="min-w-0">
                <dt className={detailTermClassName}>Completion deadline</dt>
                <dd className={detailValueClassName}>
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

      <nav aria-label="Investigation sections" className="flex flex-wrap gap-2 rounded-xl border border-[#dce4ef] bg-white p-2 text-[12px] font-medium">
        <a href="#overview" className="rounded-lg bg-[#eaf1ff] px-3 py-2 text-[#2452a4] no-underline hover:bg-[#dce9ff]">Overview</a>
        {canManage && PLANNING_ENABLED && <a href="#location" className="rounded-lg px-3 py-2 text-[#526784] no-underline hover:bg-[#f2f6fc]">Location</a>}
        {canManage && <a href="#assignment" className="rounded-lg px-3 py-2 text-[#526784] no-underline hover:bg-[#f2f6fc]">Assignment</a>}
        <a href="#report" className="rounded-lg px-3 py-2 text-[#526784] no-underline hover:bg-[#f2f6fc]">Report and history</a>
      </nav>

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
      <div className={`investigation-workspace-grid grid min-w-0 items-start gap-5 max-[980px]:grid-cols-1 ${canManage ? "grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]" : "grid-cols-1"}`}>
        {canManage && (
          <div className="investigation-workspace-column investigation-planning-column grid min-w-0 content-start gap-4 max-[767px]:gap-3">
            {PLANNING_ENABLED && (
              <LocationConfirmationPanel
                token={token}
                investigation={investigation}
                onChanged={handleChanged}
              />
            )}
            <div id="assignment" className="min-w-0">
              <AssignmentPanel
                token={token}
                investigation={investigation}
                onChanged={handleChanged}
              />
            </div>
          </div>
        )}
        <div
          id="report"
          className={`investigation-workspace-column investigation-report-column grid min-w-0 content-start gap-5 max-[767px]:gap-4 ${canManage ? "" : "mx-auto w-full max-w-[1080px]"}`}
        >
          {user.role === "agent" && (
            <ReportEditor
              token={token}
              investigation={investigation}
              onChanged={handleChanged}
              canViewEarlierReportVersions={agentPermissions?.["investigation.view_own_history"] ?? false}
              canRequestRevisit={agentPermissions?.["investigation.request_revisit"] ?? true}
            />
          )}
          {user.role === "agent" && agentPermissions?.["investigation.view_own_history"] && (
            <InvestigationActivityTimeline token={token} investigationId={investigation.id} refreshKey={activityRefreshKey} />
          )}

          {(user.role === "supervisor" || user.role === "admin") && (
            <ReviewPanel
              token={token}
              investigation={investigation}
              onChanged={handleChanged}
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
