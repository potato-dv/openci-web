import { useEffect, useMemo, useRef, useState } from "react";
import { UsersRound } from "lucide-react";

import {
  assignInvestigation,
  getAssignments,
  retryInvestigationRoute,
  submitAutomaticAssignment,
  unassignInvestigation,
} from "@/features/investigations/api";
import { getAgentRoster } from "@/features/agents/api";
import type { AgentRosterRow, Assignment, AssignmentRouteRefresh, Investigation } from "@/types/api";
import { formatUserName } from "@/utils/userName";
import { routeRefreshErrorCopy } from "@/utils/routeRefresh";
import { manilaToday } from "@/utils/format";
import { ConfirmDialog } from "@/components/ui/Primitives";

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
  const [agents, setAgents] = useState<AgentRosterRow[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [agentId, setAgentId] = useState("");
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [unassigning, setUnassigning] = useState(false);
  const [submittingAutomatic, setSubmittingAutomatic] = useState(false);
  const [automaticAssignmentMessage, setAutomaticAssignmentMessage] = useState("");
  const [confirmUnassign, setConfirmUnassign] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState("");
  const [assignmentDataRevision, setAssignmentDataRevision] = useState(0);
  const loadedInvestigationIdRef = useRef<number | null>(null);
  const activeRouteRefreshRef = useRef(false);
  const activeAssignment = useMemo(
    () => assignments.find((assignment) => assignment.is_active) ?? null,
    [assignments],
  );
  const routeRefresh = activeAssignment?.route_refresh ?? null;
  const isRouteRefreshActive = routeRefresh?.status === "queued" || routeRefresh?.status === "running";

  useEffect(() => {
    activeRouteRefreshRef.current = isRouteRefreshActive;
  }, [isRouteRefreshActive]);

  useEffect(() => {
    let cancelled = false;
    let inFlight = false;
    let activeController: AbortController | null = null;
    let lastUpdatedAt = loadedInvestigationIdRef.current === investigation.id ? Date.now() : 0;
    const initiallyLoaded = loadedInvestigationIdRef.current === investigation.id;
    setLoading(!initiallyLoaded);

    async function loadAssignmentData(showInitialLoading = false) {
      if (cancelled || inFlight) return;
      inFlight = true;
      if (showInitialLoading && loadedInvestigationIdRef.current !== investigation.id) {
        setLoading(true);
      }
      setError("");
      const controller = new AbortController();
      activeController = controller;

      try {
        const params = new URLSearchParams({ work_date: manilaToday() });
        params.set("investigation_id", String(investigation.id));
        const [rosterData, assignmentData] = await Promise.all([
          canAssign
            ? getAgentRoster(token, params, controller.signal)
            : Promise.resolve([]),
          getAssignments(token, investigation.id, controller.signal),
        ]);

        if (!cancelled) {
          setAgents(rosterData.filter((row) => row.agent.is_active));
          setAssignments(assignmentData);
          loadedInvestigationIdRef.current = investigation.id;
          lastUpdatedAt = Date.now();
        }
      } catch (err) {
        if (!cancelled && !controller.signal.aborted) {
          setError(
            err instanceof Error ? err.message : "Could not load assignments.",
          );
        }
      } finally {
        inFlight = false;
        if (activeController === controller) activeController = null;
        if (!cancelled && loadedInvestigationIdRef.current === investigation.id) setLoading(false);
      }
    }

    void loadAssignmentData(!initiallyLoaded);
    const refreshIfStale = () => {
      if (
        document.visibilityState === "visible" &&
        !activeRouteRefreshRef.current &&
        Date.now() - lastUpdatedAt >= 60_000
      ) {
        void loadAssignmentData(!loadedInvestigationIdRef.current || loadedInvestigationIdRef.current !== investigation.id);
      }
    };
    window.addEventListener("focus", refreshIfStale);
    document.addEventListener("visibilitychange", refreshIfStale);
    window.addEventListener("online", refreshIfStale);

    return () => {
      cancelled = true;
      activeController?.abort();
      window.removeEventListener("focus", refreshIfStale);
      document.removeEventListener("visibilitychange", refreshIfStale);
      window.removeEventListener("online", refreshIfStale);
    };
  }, [canAssign, investigation.id, investigation.region_code, token, assignmentDataRevision]);

  useEffect(() => {
    if (!isRouteRefreshActive) {
      return;
    }

    let cancelled = false;
    let timer: number | undefined;
    let activePollController: AbortController | null = null;
    const clearTimer = () => {
      if (timer !== undefined) window.clearTimeout(timer);
      timer = undefined;
    };
    const schedule = (delay: number) => {
      clearTimer();
      if (document.visibilityState === "visible") {
        timer = window.setTimeout(() => void poll(), delay);
      }
    };
    const poll = async () => {
      if (cancelled || document.visibilityState !== "visible") return;
      const controller = new AbortController();
      activePollController = controller;
      try {
        const assignmentData = await getAssignments(token, investigation.id, controller.signal);
        if (cancelled) return;
        setAssignments(assignmentData);
        const refreshed = assignmentData.find((assignment) => assignment.is_active)?.route_refresh;
        if (refreshed && ["queued", "running"].includes(refreshed.status)) {
          schedule(1400);
        }
      } catch {
        if (!cancelled) schedule(3000);
      } finally {
        if (activePollController === controller) activePollController = null;
      }
    };

    const resumePolling = () => {
      if (document.visibilityState === "visible") void poll();
      else clearTimer();
    };
    document.addEventListener("visibilitychange", resumePolling);
    schedule(1200);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", resumePolling);
      clearTimer();
      activePollController?.abort();
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
      setAssignmentDataRevision((current) => current + 1);
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
      setAssignmentDataRevision((current) => current + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not retry the route update.");
    } finally {
      setRetrying(false);
    }
  }

  async function handleUnassign() {
    setUnassigning(true);
    setError("");
    try {
      await unassignInvestigation(token, investigation.id);
      setAssignments((current) =>
        current.map((assignment) =>
          assignment.is_active
            ? { ...assignment, is_active: false }
            : assignment,
        ),
      );
      setAgentId("");
      setNote("");
      setConfirmUnassign(false);
      onChanged();
      setAssignmentDataRevision((current) => current + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not unassign case.");
    } finally {
      setUnassigning(false);
    }
  }

  async function handleSubmitAutomaticAssignment() {
    setSubmittingAutomatic(true);
    setError("");
    setAutomaticAssignmentMessage("");
    try {
      await submitAutomaticAssignment(token, investigation.id);
      setAutomaticAssignmentMessage(
        "Submitted for automatic assignment. Only an eligible agent within the 10 km depot radius will be considered.",
      );
      onChanged();
      setAssignmentDataRevision((current) => current + 1);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not submit automatic assignment.",
      );
    } finally {
      setSubmittingAutomatic(false);
    }
  }

  const selectedAgent = agents.find((row) => String(row.agent.id) === agentId);
  const routeStatusCopy = routeRefresh ? getRouteRefreshCopy(routeRefresh) : null;
  const routeRetryable = routeRefresh && ["failed", "partially_published", "unscheduled"].includes(routeRefresh.status);

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
                  ? "Manual override. All active agents can be selected; route availability is checked separately."
                  : "Assignment is closed while this investigation is being handled or reviewed."}
              </p>
            </div>
          </div>
        </div>
        {canAssign && activeAssignment && (
          <button
            type="button"
            className="danger-button compact-button"
            onClick={() => {
              setError("");
              setConfirmUnassign(true);
            }}
            disabled={unassigning}
          >
            Unassign
          </button>
        )}
      </div>

      {automaticAssignmentMessage && (
        <p className="form-hint" role="status">
          {automaticAssignmentMessage}
        </p>
      )}
      {investigation.manual_assignment_required &&
        investigation.assigned_agent_id == null &&
        !automaticAssignmentMessage && (
          <div className="workflow-actions">
            <p className="form-hint" role="status">
              Automatic assignment is paused. Submit this case to let the planner assign it again.
            </p>
            <button
              type="button"
              className="primary-button compact-button"
              onClick={() => void handleSubmitAutomaticAssignment()}
              disabled={submittingAutomatic || !investigation.location_confirmed}
            >
              {submittingAutomatic
                ? "Submitting…"
                : "Submit for automatic assignment"}
            </button>
            {!investigation.location_confirmed && (
              <p className="form-hint">
                Confirm the investigation location before submitting it for automatic assignment.
              </p>
            )}
          </div>
        )}

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
              {agents.map(({ agent, configured_region_name, configured_region_code }) => (
                <option key={agent.id} value={agent.id}>
                  {formatUserName(agent.name)} · {configured_region_name ?? configured_region_code ?? "No region"}
                </option>
              ))}
            </select>
          </div>

          {selectedAgent && (
            <p className="form-hint">
              Region: {selectedAgent.configured_region_name ?? selectedAgent.configured_region_code ?? "Not configured"} · Depot: {selectedAgent.depot_label ?? (
                selectedAgent.depot_latitude != null && selectedAgent.depot_longitude != null
                  ? `${selectedAgent.depot_latitude.toFixed(4)}, ${selectedAgent.depot_longitude.toFixed(4)}`
                  : "Not configured"
              )} · {selectedAgent.assigned_workload_count} open cases · {selectedAgent.visit_workload_count} visits{selectedAgent.shift ? ` / ${selectedAgent.shift.max_visits} today` : ""}
            </p>
          )}
          {selectedAgent?.outside_configured_region && (
            <p className="form-hint">This investigation is outside the agent’s configured region. Manual assignment can still proceed.</p>
          )}
          {selectedAgent?.outside_service_radius && (
            <p className="form-hint">This investigation is {(selectedAgent.depot_distance_metres! / 1000).toFixed(1)} km from the configured depot, outside the normal 10 km automatic service radius. Manual assignment can still proceed.</p>
          )}
          {selectedAgent && !selectedAgent.shift && (
            <p className="form-hint">No shift is configured for this date. The assignment can be saved, but a route may not be available today.</p>
          )}
          {selectedAgent && investigation.location_confirmed && selectedAgent.depot_distance_metres == null && (
            <p className="form-hint">The depot distance cannot be assessed for this date. Manual assignment can still proceed.</p>
          )}

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
            disabled={loading || saving || !agents.length || !investigation.location_confirmed}
          >
            {saving ? "Applying override…" : "Apply manual override"}
          </button>
          {!investigation.location_confirmed && <p className="form-hint">Confirm the investigation location before assigning an agent.</p>}
          {investigation.location_confirmed && !agents.length && <p className="form-hint">No active agents are available.</p>}
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
                {assignment.route_refresh?.status === "unscheduled" ? " · assigned — unscheduled" : ""}
              </li>
            ))}
          </ul>
        ) : (
          <p className="empty-state">No assignment history yet.</p>
        )}
      </details>
      <ConfirmDialog
        open={confirmUnassign}
        title="Unassign investigation"
        action="Unassign"
        danger
        busy={unassigning}
        onClose={() => setConfirmUnassign(false)}
        onConfirm={() => void handleUnassign()}
      >
        <p>
          End <strong>{investigation.reference_number}</strong>’s current
          assignment? Its history will be kept, and automatic assignment will
          remain paused until you choose an agent manually.
        </p>
        {error && <p className="error" role="alert">{error}</p>}
      </ConfirmDialog>
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
    case "unscheduled":
      return {
        title: "Assigned — Unscheduled",
        message: "The manual assignment is saved. No feasible stop fits the current route; route actions remain unavailable until a validated route includes this investigation.",
      };
  }
}
