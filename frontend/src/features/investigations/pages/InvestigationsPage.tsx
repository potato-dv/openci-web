import { useCallback, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { Plus, RefreshCw } from "lucide-react";
import { useSession } from "@/app/session";
import {
  deleteInvestigation,
  getInvestigations,
  submitAutomaticAssignment,
  unassignInvestigation,
} from "@/features/investigations/api";
import { getAgents } from "@/features/agents/api";
import { useResource } from "@/hooks/useResource";
import { InvestigationTable } from "@/components/data/InvestigationTable";
import {
  DataFilterBar,
  dataFilterFieldClassName,
  dataFilterSearchClassName,
} from "@/components/data/DataFilterBar";
import { Pagination } from "@/components/data/Pagination";
import { PageHeader } from "@/components/layout/PageHeader";
import {
  Button,
  ConfirmDialog,
  EmptyState,
  InlineAlert,
  Skeleton,
  ToastRegion,
} from "@/components/ui/Primitives";
import type { Investigation } from "@/types/api";
export function InvestigationsPage() {
  const { token, user, agentPermissions } = useSession();
  const [params, setParams] = useSearchParams();
  const key = params.toString();
  const resource = useResource(
    useCallback(
      (signal) => getInvestigations(token, new URLSearchParams(key), signal),
      [token, key],
    ),
  );
  const agents = useResource(
    useCallback(
      async () =>
        user.role === "admin" || user.role === "supervisor"
          ? getAgents(token)
          : [],
      [token, user.role],
    ),
  );
  const [trash, setTrash] = useState<Investigation | null>(null);
  const [unassignTarget, setUnassignTarget] = useState<Investigation | null>(null);
  const [automaticAssignmentBusyId, setAutomaticAssignmentBusyId] = useState<number | null>(null);
  const [automaticAssignmentSubmittedId, setAutomaticAssignmentSubmittedId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [unassignBusy, setUnassignBusy] = useState(false);
  const [error, setError] = useState("");
  const [unassignError, setUnassignError] = useState("");
  const [automaticAssignmentError, setAutomaticAssignmentError] = useState("");
  const [message, setMessage] = useState("");
  function update(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    if (name !== "page") next.delete("page");
    setParams(next, { replace: name === "q" });
  }
  const manage = user.role === "admin" || user.role === "supervisor";
  async function remove() {
    if (!trash) return;
    setBusy(true);
    setError("");
    try {
      await deleteInvestigation(token, trash.id);
      setMessage(`${trash.reference_number} moved to Trash.`);
      setTrash(null);
      resource.refresh();
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Could not move this record to Trash.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function unassign() {
    if (!unassignTarget) return;
    setUnassignBusy(true);
    setUnassignError("");
    try {
      await unassignInvestigation(token, unassignTarget.id);
      setAutomaticAssignmentSubmittedId((current) =>
        current === unassignTarget.id ? null : current,
      );
      setMessage(
        `${unassignTarget.reference_number} is unassigned. Choose a new agent from its assignment panel.`,
      );
      setUnassignTarget(null);
      resource.refresh();
    } catch (error) {
      setUnassignError(
        error instanceof Error
          ? error.message
          : "Could not unassign this investigation.",
      );
    } finally {
      setUnassignBusy(false);
    }
  }
  async function submitForAutomaticAssignment(item: Investigation) {
    if (automaticAssignmentBusyId != null) return;
    setAutomaticAssignmentBusyId(item.id);
    setAutomaticAssignmentError("");
    try {
      await submitAutomaticAssignment(token, item.id);
      setAutomaticAssignmentSubmittedId(item.id);
      setMessage(
        `${item.reference_number} was submitted for automatic assignment. Only an eligible agent within the 10 km depot radius will be considered.`,
      );
      resource.refresh();
    } catch (error) {
      setAutomaticAssignmentError(
        error instanceof Error
          ? error.message
          : "Could not submit this investigation for automatic assignment.",
      );
    } finally {
      setAutomaticAssignmentBusyId(null);
    }
  }
  return (
    <>
      <PageHeader
        title="Investigations"
        description="Manage investigation records, assignments, and progress."
        actions={
          <>
            <Button onClick={resource.refresh} disabled={resource.loading}>
              <RefreshCw size={16} aria-hidden="true" />
              Refresh
            </Button>
            {manage && (
              <>
                <Link className="secondary-button" to="/investigations/trash">
                  Trash
                </Link>
                <Link className="primary-button" to="/investigations/new">
                  <Plus size={16} aria-hidden="true" />
                  New investigation
                </Link>
              </>
            )}
          </>
        }
      />
      <section className="content-card data-section">
        <DataFilterBar>
          <label className={dataFilterSearchClassName}>
            Search
            <input
              type="search"
              placeholder="Reference, subject, or address"
              value={params.get("q") ?? ""}
              onChange={(event) => update("q", event.target.value)}
            />
          </label>
          <label className={dataFilterFieldClassName}>
            Status
            <select
              value={params.get("status") ?? ""}
              onChange={(event) => update("status", event.target.value)}
            >
              <option value="">All statuses</option>
              {[
                "pending",
                "assigned",
                "in_progress",
                "under_review",
                "returned_for_correction",
                "completed",
                "cancelled",
              ].filter((status) => status !== "completed" || manage || (agentPermissions?.["investigation.view_own_history"] ?? false)).map((status) => (
                <option key={status} value={status}>
                  {status.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
          <label className={dataFilterFieldClassName}>
            Priority
            <select
              value={params.get("priority") ?? ""}
              onChange={(event) => update("priority", event.target.value)}
            >
              <option value="">All priorities</option>
              <option value="normal">Normal</option>
              <option value="high">High</option>
              <option value="urgent">Urgent</option>
            </select>
          </label>
          <label className={dataFilterFieldClassName}>
            Location
            <select
              value={params.get("location_confirmed") ?? ""}
              onChange={(event) =>
                update("location_confirmed", event.target.value)
              }
            >
              <option value="">All locations</option>
              <option value="true">Confirmed</option>
              <option value="false">Unconfirmed</option>
            </select>
          </label>
          {manage && (
            <label className={dataFilterFieldClassName}>
              Agent
              <select
                value={params.get("assigned_agent_id") ?? ""}
                onChange={(event) =>
                  update("assigned_agent_id", event.target.value)
                }
              >
                <option value="">All agents</option>
                <option value="0">Unassigned</option>
                {agents.data?.map((agent) => (
                  <option value={agent.id} key={agent.id}>
                    {agent.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <Button disabled={!key} onClick={() => setParams({})}>
            Clear
          </Button>
        </DataFilterBar>
        {resource.error && (
          <InlineAlert onRetry={resource.refresh}>{resource.error}</InlineAlert>
        )}
        {automaticAssignmentError && (
          <InlineAlert>{automaticAssignmentError}</InlineAlert>
        )}
        {resource.loading ? (
          <Skeleton />
        ) : (
          resource.data && (
            <>
              {resource.data.items.length ? (
                <InvestigationTable
                  items={resource.data.items}
                  canManage={manage}
                  sort={params.get("sort") ?? "created_at"}
                  direction={params.get("direction") ?? "desc"}
                  onSort={(column) => {
                    const next = new URLSearchParams(params);
                    next.set("sort", column);
                    next.set(
                      "direction",
                      params.get("sort") === column &&
                        params.get("direction") === "asc"
                        ? "desc"
                        : "asc",
                    );
                    next.delete("page");
                    setParams(next);
                  }}
                  onTrash={setTrash}
                  onUnassign={(item) => {
                    setUnassignError("");
                    setAutomaticAssignmentSubmittedId((current) =>
                      current === item.id ? null : current,
                    );
                    setUnassignTarget(item);
                  }}
                  onSubmitAutomaticAssignment={(item) =>
                    void submitForAutomaticAssignment(item)
                  }
                  automaticAssignmentBusyId={automaticAssignmentBusyId}
                  automaticAssignmentSubmittedId={automaticAssignmentSubmittedId}
                />
              ) : (
                <EmptyState
                  title={
                    key ? "No matching investigations" : "No investigations yet"
                  }
                >
                  {key
                    ? "Try a different search or clear the filters."
                    : manage
                      ? "Create an investigation to begin assigning field work."
                      : "Assigned investigations will appear here."}
                </EmptyState>
              )}
              <Pagination
                total={resource.data.total}
                page={resource.data.page}
                pageSize={resource.data.page_size}
                onChange={(page) => update("page", String(page))}
                onSizeChange={(size) => update("page_size", String(size))}
              />
            </>
          )
        )}
      </section>
      <ConfirmDialog
        open={Boolean(trash)}
        title="Move investigation to Trash"
        action="Move to Trash"
        danger
        busy={busy}
        onClose={() => setTrash(null)}
        onConfirm={() => void remove()}
      >
        <p>
          Move <strong>{trash?.reference_number}</strong> to Trash? Its history
          will be retained and it can be restored.
        </p>
        {error && <InlineAlert>{error}</InlineAlert>}
      </ConfirmDialog>
      <ConfirmDialog
        open={Boolean(unassignTarget)}
        title="Unassign investigation"
        action="Unassign"
        danger
        busy={unassignBusy}
        onClose={() => setUnassignTarget(null)}
        onConfirm={() => void unassign()}
      >
        <p>
          End <strong>{unassignTarget?.reference_number}</strong>’s current
          assignment? The assignment history will be kept. Automatic assignment
          will stay paused until you choose an agent manually.
        </p>
        {unassignError && <InlineAlert>{unassignError}</InlineAlert>}
      </ConfirmDialog>
      <ToastRegion message={message} onDismiss={() => setMessage("")} />
    </>
  );
}
