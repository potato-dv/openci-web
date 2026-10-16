import { useEffect, useState } from "react";

import {
  assignInvestigation,
  getAgents,
  getAssignments,
} from "../../services/api";
import type { Assignment, Investigation, User } from "../../types/api";
import { formatUserName } from "../../utils/userName";

type AssignmentPanelProps = {
  token: string;
  investigation: Investigation;
  onChanged: () => void;
};

export function AssignmentPanel({
  token,
  investigation,
  onChanged,
}: AssignmentPanelProps) {
  const canAssign = ["pending", "assigned"].includes(investigation.status);
  const [agents, setAgents] = useState<User[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [agentId, setAgentId] = useState("");
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadAssignmentData() {
      setLoading(true);
      setError("");

      try {
        const [agentData, assignmentData] = await Promise.all([
          canAssign ? getAgents(token) : Promise.resolve([]),
          getAssignments(token, investigation.id),
        ]);

        if (!cancelled) {
          setAgents(agentData);
          setAssignments(assignmentData);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Could not load assignments.",
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadAssignmentData();

    return () => {
      cancelled = true;
    };
  }, [canAssign, investigation.id, token]);

  async function handleAssign() {
    if (!agentId) {
      setError("Select an agent before assigning this investigation.");
      return;
    }

    setSaving(true);
    setError("");

    try {
      const assignment = await assignInvestigation(
        token,
        investigation.id,
        Number(agentId),
        note.trim() || undefined,
      );
      setAssignments((current) => [assignment, ...current]);
      setNote("");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not assign case.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="workflow-panel">
      <div className="section-heading">
        <div>
          <h3>Agent assignment</h3>
          <p>
            {canAssign
              ? "Assign or reassign an eligible field agent."
              : "Assignment is closed while this investigation is being handled or reviewed."}
          </p>
        </div>
      </div>

      {canAssign && (
        <>
          <div className="workflow-form-row">
            <label htmlFor="assignment-agent">Agent</label>
            <select
              id="assignment-agent"
              value={agentId}
              onChange={(event) => setAgentId(event.target.value)}
              disabled={loading || saving}
            >
              <option value="">Select an agent</option>
              {agents.map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {formatUserName(agent.name)} ({agent.email})
                </option>
              ))}
            </select>
          </div>

          <div className="workflow-form-row">
            <label htmlFor="assignment-note">Assignment note</label>
            <input
              id="assignment-note"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Optional instructions"
              maxLength={500}
              disabled={saving}
            />
          </div>

          {error && <p className="error" role="alert">{error}</p>}

          <button
            type="button"
            className="primary-button compact-button"
            onClick={() => void handleAssign()}
            disabled={loading || saving || !agents.length}
          >
            {saving ? "Assigning..." : "Assign investigation"}
          </button>
        </>
      )}

      <details
        key={`${investigation.id}-${canAssign ? "assignable" : "closed"}`}
        className="workflow-history"
        open={canAssign || undefined}
      >
        <summary>Assignment history ({assignments.length})</summary>
        {loading ? (
          <p className="muted">Loading assignment history…</p>
        ) : assignments.length > 0 ? (
          <ul>
            {assignments.map((assignment) => (
              <li key={assignment.id}>
                {formatUserName(assignment.agent_name)} · assigned by {formatUserName(assignment.assigned_by_name)}
                {assignment.is_active ? " · active" : " · ended"}
              </li>
            ))}
          </ul>
        ) : (
          <p className="empty-state">No assignment history yet.</p>
        )}
      </details>
    </section>
  );
}
