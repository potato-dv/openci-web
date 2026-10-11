import type { Investigation, User } from "../types/api";
import { AssignmentPanel } from "../components/investigations/AssignmentPanel";
import { ReportEditor } from "../components/investigations/ReportEditor";
import { ReviewPanel } from "../components/investigations/ReviewPanel";
import { StatusBadge } from "../components/ui/StatusBadge";

type InvestigationDetailsPageProps = {
  token: string;
  user: User;
  investigation: Investigation;
  onChanged: () => void;
};

export function InvestigationDetailsPage({
  token,
  user,
  investigation,
  onChanged,
}: InvestigationDetailsPageProps) {
  return (
    <div className="details-layout">
      <section className="details-summary">
        <div className="section-heading">
          <div>
            <p className="eyebrow">SELECTED INVESTIGATION</p>
            <h2>{investigation.reference_number}</h2>
            <p>{investigation.subject_name}</p>
          </div>
          <StatusBadge status={investigation.status} />
        </div>
        <dl className="details-grid">
          <div>
            <dt>Address</dt>
            <dd>{investigation.address}</dd>
          </div>
          <div>
            <dt>Priority</dt>
            <dd className={`priority-${investigation.priority}`}>
              {investigation.priority}
            </dd>
          </div>
          <div>
            <dt>Assigned agent</dt>
            <dd>{investigation.assigned_agent_id ?? "Unassigned"}</dd>
          </div>
        </dl>
      </section>

      {user.role === "supervisor" && (
        <AssignmentPanel
          token={token}
          investigation={investigation}
          onChanged={onChanged}
        />
      )}

      {user.role === "agent" && (
        <ReportEditor
          token={token}
          investigation={investigation}
          onChanged={onChanged}
        />
      )}

      {user.role === "supervisor" && (
        <ReviewPanel
          token={token}
          investigation={investigation}
          onChanged={onChanged}
        />
      )}
    </div>
  );
}
