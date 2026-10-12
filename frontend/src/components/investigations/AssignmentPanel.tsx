import { useEffect, useState } from "react";

import {
  assignInvestigation,
  getAgents,
  getAssignments,
} from "../../services/api";
import type { Assignment, Investigation, User } from "../../types/api";

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
          getAgents(token),
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
  }, [investigation.id, token]);

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

  const activeAssignment = assignments.find((item) => item.is_active);

  return (
    <section className="workflow-panel">
      <div className="section-heading">
        <div>
          <h3>Agent assignment</h3>
          <p>Assign or reassign an eligible field agent.</p>
        </div>
      </div>

      {activeAssignment && (
        <p className="workflow-meta">
          Current agent: <strong>{activeAssignment.agent_name}</strong>
        </p>
      )}

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
              {agent.name} ({agent.email})
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

      {error && <p className="error">{error}</p>}

      <button
        type="button"
        className="primary-button compact-button"
        onClick={() => void handleAssign()}
        disabled={loading || saving || !agents.length}
      >
        {saving ? "Assigning..." : "Assign investigation"}
      </button>

      {assignments.length > 0 && (
        <div className="workflow-history">
          <h4>Assignment history</h4>
          <ul>
            {assignments.map((assignment) => (
              <li key={assignment.id}>
                {assignment.agent_name} · assigned by {assignment.assigned_by_name}
                {assignment.is_active ? " · active" : " · ended"}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
