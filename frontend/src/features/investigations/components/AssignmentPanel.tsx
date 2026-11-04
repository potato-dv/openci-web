import { useEffect, useMemo, useState } from "react";
import { UsersRound } from "lucide-react";

import {
  assignInvestigation,
  getAssignments,
  retryInvestigationRoute,
} from "@/features/investigations/api";
import { getAgentRoster } from "@/features/agents/api";
import type { AgentRosterRow, Assignment, AssignmentRouteRefresh, Investigation } from "@/types/api";
import { formatUserName } from "@/utils/userName";
import { routeRefreshErrorCopy } from "@/utils/routeRefresh";
import { manilaToday } from "@/utils/format";

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
  const [eligibleAgents, setEligibleAgents] = useState<AgentRosterRow[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [agentId, setAgentId] = useState("");
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState("");
  const activeAssignment = useMemo(
    () => assignments.find((assignment) => assignment.is_active) ?? null,
    [assignments],
  );
  const routeRefresh = activeAssignment?.route_refresh ?? null;
  const isRouteRefreshActive = routeRefresh?.status === "queued" || routeRefresh?.status === "running";

  useEffect(() => {
    let cancelled = false;

    async function loadAssignmentData() {
      setLoading(true);
      setError("");

      try {
        const params = new URLSearchParams({ work_date: manilaToday() });
        if (investigation.region_code) params.set("region_code", investigation.region_code);
        const [rosterData, assignmentData] = await Promise.all([
          canAssign && investigation.region_code
            ? getAgentRoster(token, params)
            : Promise.resolve([]),
          getAssignments(token, investigation.id),
        ]);

        if (!cancelled) {
          setEligibleAgents(rosterData.filter((row) => {
            const shift = row.shift;
            const isCurrentAgent = row.agent.id === investigation.assigned_agent_id;
            return Boolean(
              row.agent.is_active &&
              shift?.is_available &&
              shift.region_code === investigation.region_code &&
              (isCurrentAgent || (
                row.assigned_workload_count < shift.max_open_cases &&
                row.visit_workload_count < shift.max_visits
              )),
            );
          }));
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
  }, [canAssign, investigation.assigned_agent_id, investigation.id, investigation.region_code, token]);

  useEffect(() => {
    if (!isRouteRefreshActive) {
      return;
    }

    let cancelled = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const assignmentData = await getAssignments(token, investigation.id);
        if (cancelled) return;
        setAssignments(assignmentData);
        const refreshed = assignmentData.find((assignment) => assignment.is_active)?.route_refresh;
        if (refreshed && ["queued", "running"].includes(refreshed.status)) {
          timer = window.setTimeout(() => void poll(), 1400);
        }
      } catch {
        if (!cancelled) timer = window.setTimeout(() => void poll(), 3000);
      }
    };

    timer = window.setTimeout(() => void poll(), 1200);
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [activeAssignment?.id, investigation.id, isRouteRefreshActive, token]);

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
      setAssignments((current) => [
        assignment,
        ...current
          .filter((item) => item.id !== assignment.id)
          .map((item) => item.is_active ? { ...item, is_active: false } : item),
      ]);
      setNote("");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not assign case.");
    } finally {
      setSaving(false);
    }
  }

  async function handleRetryRoute() {
    setRetrying(true);
    setError("");
    try {
      const assignment = await retryInvestigationRoute(token, investigation.id);
      setAssignments((current) => [
        assignment,
        ...current
          .filter((item) => item.id !== assignment.id)
          .map((item) => item.is_active ? { ...item, is_active: false } : item),
      ]);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not retry the route update.");
    } finally {
      setRetrying(false);
    }
  }

  const routeStatusCopy = routeRefresh ? getRouteRefreshCopy(routeRefresh) : null;
  const routeRetryable = routeRefresh && ["failed", "partially_published"].includes(routeRefresh.status);

  return (
    <section className="workflow-panel investigation-assignment-panel">
      <div className="section-heading">
        <div>
          <div className="workflow-title">
            <span className="workflow-title-icon" aria-hidden="true">
              <UsersRound size={17} strokeWidth={2} />
            </span>
            <div>
              <h3>Agent assignment</h3>
              <p>
                {canAssign
                  ? "Manual override. Only active agents with an available matching shift and remaining capacity are listed."
                  : "Assignment is closed while this investigation is being handled or reviewed."}
              </p>
            </div>
          </div>
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
              {eligibleAgents.map(({ agent, shift, assigned_workload_count, visit_workload_count }) => (
                <option key={agent.id} value={agent.id}>
                  {formatUserName(agent.name)} · {assigned_workload_count}/{shift?.max_open_cases ?? "—"} open · {visit_workload_count}/{shift?.max_visits ?? "—"} visits
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

          <button
            type="button"
            className="primary-button compact-button"
            onClick={() => void handleAssign()}
            disabled={loading || saving || !eligibleAgents.length || !investigation.location_confirmed}
          >
            {saving ? "Applying override…" : "Apply manual override"}
          </button>
          {!investigation.location_confirmed && <p className="form-hint">Confirm the investigation location before assigning an agent.</p>}
          {investigation.location_confirmed && !eligibleAgents.length && <p className="form-hint">No active agent has an available matching shift with remaining capacity today.</p>}
        </>
      )}

      {error && <p className="error" role="alert">{error}</p>}

      {routeStatusCopy && routeRefresh && (
        <div
          className={`assignment-route-status is-${routeRefresh.status}`}
          role={routeRetryable ? "alert" : "status"}
          aria-live={routeRetryable ? "assertive" : "polite"}
        >
          <div className="assignment-route-status-copy">
            <strong>{routeStatusCopy.title}</strong>
            <p>{routeStatusCopy.message}</p>
            {(routeRefresh.errors ?? []).length > 0 && (
              <ul>
                {[...new Set((routeRefresh.errors ?? []).map(routeRefreshErrorCopy))].map((message) => (
                  <li key={message}>{message}</li>
                ))}
              </ul>
            )}
          </div>
          {routeRetryable && (
            <button
              type="button"
              className="secondary-button compact-button"
              onClick={() => void handleRetryRoute()}
              disabled={retrying}
            >
              {retrying ? "Retrying…" : "Retry route"}
            </button>
          )}
        </div>
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
                {assignment.assignment_source === "manual" ? "Manual override" : "Automatic assignment"} · {formatUserName(assignment.agent_name)} · assigned by {formatUserName(assignment.assigned_by_name)}
                {assignment.is_active ? " · active" : " · ended"}
                {assignment.route_refresh?.status === "published" ? " · route published" : ""}
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

function getRouteRefreshCopy(routeRefresh: AssignmentRouteRefresh) {
  switch (routeRefresh.status) {
    case "queued":
      return {
        title: "Route update queued",
        message: "The assignment is saved. Today’s route is being rebuilt for the affected agents.",
      };
    case "running":
      return {
        title: "Building today’s route",
        message: "The agent’s published route will update after the road route is validated.",
      };
    case "published":
      return {
        title: "Route published",
        message: "Today’s validated road route is now available to the agent.",
      };
    case "partially_published":
      return {
        title: "Some routes need attention",
        message: "The assignment is saved, but one or more affected routes could not be updated.",
      };
    case "failed":
      return {
        title: "Route update failed",
        message: "The assignment is saved, but no new route was published. Fix the issue and retry.",
      };
  }
}
