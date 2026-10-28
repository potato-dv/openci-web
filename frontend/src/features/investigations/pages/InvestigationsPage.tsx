import { useCallback, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { Plus, RefreshCw } from "lucide-react";
import { useSession } from "@/app/session";
import {
  deleteInvestigation,
  getInvestigations,
} from "@/features/investigations/api";
import { getAgents } from "@/features/agents/api";
import { useResource } from "@/hooks/useResource";
import { InvestigationTable } from "@/components/data/InvestigationTable";
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
  const { token, user } = useSession();
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
      async () => (user.role !== "agent" ? getAgents(token) : []),
      [token, user.role],
    ),
  );
  const [trash, setTrash] = useState<Investigation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  function update(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    if (name !== "page") next.delete("page");
    setParams(next, { replace: name === "q" });
  }
  const manage = user.role !== "agent";
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
        <div className="data-filters">
          <label className="filter-search">
            Search
            <input
              type="search"
              placeholder="Reference, subject, or address"
              value={params.get("q") ?? ""}
              onChange={(event) => update("q", event.target.value)}
            />
          </label>
          <label>
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
              ].map((status) => (
                <option key={status} value={status}>
                  {status.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
          <label>
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
          <label>
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
            <label>
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
        </div>
        {resource.error && (
          <InlineAlert onRetry={resource.refresh}>{resource.error}</InlineAlert>
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
      <ToastRegion message={message} onDismiss={() => setMessage("")} />
    </>
  );
}
