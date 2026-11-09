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
import { WorkspacePanel } from "@/components/layout/WorkspacePanel";
import { ResourceFreshness } from "@/components/data/ResourceFreshness";
import { WorkspaceSelect } from "@/components/ui/WorkspaceSelect";
import { WorkspaceSearchField } from "@/components/data/WorkspaceSearchField";
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
    {
      resourceKeys: ["investigations.list"],
      refetchOnFocus: true,
      refetchOnReconnect: true,
      staleTimeMs: 60_000,
    },
  );
  const agents = useResource(
    useCallback(
      async (signal) =>
        user.role === "admin" || user.role === "supervisor"
          ? getAgents(token, signal)
          : [],
      [token, user.role],
    ),
    {
      resourceKeys: user.role === "admin" || user.role === "supervisor" ? ["users.list"] : [],
      refetchOnFocus: true,
      refetchOnReconnect: true,
      staleTimeMs: 5 * 60_000,
    },
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
      <PageHeader title="Investigations" />
      <WorkspacePanel
        title="Investigation register"
        description="Search, filter, and update active records."
        className="data-section"
        action={
          <div className="flex w-full flex-wrap items-center justify-end gap-2 sm:w-auto">
            <ResourceFreshness
              loading={resource.refreshing || agents.refreshing}
              lastUpdatedAt={resource.lastUpdatedAt}
            />
            <Button
              onClick={() => {
                resource.refresh();
                if (manage) agents.refresh();
              }}
              disabled={resource.refreshing || (manage && agents.refreshing)}
            >
              <RefreshCw
                className={resource.refreshing || (manage && agents.refreshing) ? "animate-spin" : ""}
                size={16}
                aria-hidden="true"
              />
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
          </div>
        }
      >
        <DataFilterBar>
          <WorkspaceSearchField className={dataFilterSearchClassName} value={params.get("q") ?? ""} onChange={(value) => update("q", value)} placeholder="Reference, subject, or address" />
          <WorkspaceSelect
            className={dataFilterFieldClassName}
            label="Status"
            value={params.get("status") ?? ""}
            onValueChange={(value) => update("status", value)}
            options={[
              { value: "", label: "All statuses" },
              ...["pending", "assigned", "in_progress", "under_review", "returned_for_correction", "completed", "cancelled"]
                .filter((status) => status !== "completed" || manage || (agentPermissions?.["investigation.view_own_history"] ?? false))
                .map((status) => ({ value: status, label: status.replaceAll("_", " ") })),
            ]}
          />
          <WorkspaceSelect
            className={dataFilterFieldClassName}
            label="Priority"
            value={params.get("priority") ?? ""}
            onValueChange={(value) => update("priority", value)}
            options={[{ value: "", label: "All priorities" }, { value: "normal", label: "Normal" }, { value: "high", label: "High" }, { value: "urgent", label: "Urgent" }]}
          />
          <WorkspaceSelect
            className={dataFilterFieldClassName}
            label="Location"
            value={params.get("location_confirmed") ?? ""}
            onValueChange={(value) => update("location_confirmed", value)}
            options={[{ value: "", label: "All locations" }, { value: "true", label: "Confirmed" }, { value: "false", label: "Unconfirmed" }]}
          />
          {manage && (
            <WorkspaceSelect
              className={dataFilterFieldClassName}
              label="Agent"
              value={params.get("assigned_agent_id") ?? ""}
              onValueChange={(value) => update("assigned_agent_id", value)}
              options={[{ value: "", label: "All agents" }, { value: "0", label: "Unassigned" }, ...(agents.data?.map((agent) => ({ value: String(agent.id), label: agent.name })) ?? [])]}
            />
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
        {resource.loading && !resource.data ? (
          <Skeleton />
        ) : resource.data ? (
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
        ) : null}
      </WorkspacePanel>
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
