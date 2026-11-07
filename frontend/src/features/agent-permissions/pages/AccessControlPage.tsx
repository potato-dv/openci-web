import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button, InlineAlert, Skeleton } from "@/components/ui/Primitives";
import { getUsers } from "@/features/users/api";
import { HistoryAccessSection } from "@/features/agent-permissions/components/HistoryAccessSection";
import { PermissionFeatureRow } from "@/features/agent-permissions/components/PermissionFeatureRow";
import { PermissionHistoryPanel } from "@/features/agent-permissions/components/PermissionHistoryPanel";
import { RequiredWorkflowsPanel } from "@/features/agent-permissions/components/RequiredWorkflowsPanel";
import {
  getAgentPermissionCatalog,
  getAgentPermissionHistory,
  getAgentPermissionState,
  saveAgentPermissionState,
} from "@/features/agent-permissions/api";
import { useSession } from "@/app/session";
import type {
  AgentFeatureCode,
  AgentPermissionEffect,
  AgentPermissionFeature,
  AgentPermissionHistoryItem,
  AgentPermissionState,
  User,
} from "@/types/api";

type PermissionCatalog = {
  features: Omit<AgentPermissionFeature, "override" | "effective_allowed">[];
  mandatory_workflows: { name: string; description: string }[];
};

const HISTORY_PERMISSION_CODE: AgentFeatureCode =
  "investigation.view_own_history";

function emptyOverrides(features: PermissionCatalog["features"]) {
  return Object.fromEntries(
    features.map((feature) => [
      feature.code,
      feature.code === HISTORY_PERMISSION_CODE
        ? feature.default_allowed
          ? "allow"
          : "deny"
        : "inherit",
    ]),
  ) as Record<AgentFeatureCode, AgentPermissionEffect>;
}

export function AccessControlPage() {
  const { token } = useSession();
  const [agents, setAgents] = useState<User[]>([]);
  const [catalog, setCatalog] = useState<PermissionCatalog | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [state, setState] = useState<AgentPermissionState | null>(null);
  const [history, setHistory] = useState<AgentPermissionHistoryItem[]>([]);
  const [draft, setDraft] = useState<
    Record<AgentFeatureCode, AgentPermissionEffect>
  >({} as Record<AgentFeatureCode, AgentPermissionEffect>);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const [allUsers, nextCatalog] = await Promise.all([
          getUsers(token),
          getAgentPermissionCatalog(token),
        ]);
        if (cancelled) return;
        const agentUsers = allUsers.filter((item) => item.role === "agent");
        setAgents(agentUsers);
        setCatalog(nextCatalog);
        setSelectedId((current) =>
          current && agentUsers.some((item) => item.id === current)
            ? current
            : (agentUsers[0]?.id ?? null),
        );
      } catch (loadError) {
        if (!cancelled)
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Could not load Agent access settings.",
          );
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => {
    if (!catalog || selectedId == null) return;
    const agentId = selectedId;
    const selectedCatalog = catalog;
    let cancelled = false;
    async function loadSelectedAgent() {
      try {
        const [nextState, nextHistory] = await Promise.all([
          getAgentPermissionState(token, agentId),
          getAgentPermissionHistory(token, agentId),
        ]);
        if (cancelled) return;
        setError("");
        setState(nextState);
        setDraft({
          ...emptyOverrides(selectedCatalog.features),
          ...Object.fromEntries(
            nextState.features.map((feature) => [
              feature.code,
              feature.code === HISTORY_PERMISSION_CODE
                ? (feature.override ??
                  (feature.effective_allowed ? "allow" : "deny"))
                : (feature.override ?? "inherit"),
            ]),
          ),
        } as Record<AgentFeatureCode, AgentPermissionEffect>);
        setHistory(nextHistory.items);
      } catch (loadError) {
        if (!cancelled)
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Could not load this Agent’s permissions.",
          );
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadSelectedAgent();
    return () => {
      cancelled = true;
    };
  }, [catalog, selectedId, token]);

  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.id === selectedId),
    [agents, selectedId],
  );
  const historyFeature = state?.features.find(
    (feature) => feature.code === HISTORY_PERMISSION_CODE,
  );
  const historySelection =
    draft[HISTORY_PERMISSION_CODE] === "allow" ? "allow" : "deny";
  const historySavedSelection = historyFeature?.effective_allowed
    ? "allow"
    : "deny";
  const historyHasPendingChange = Boolean(
    historyFeature && historySelection !== historySavedSelection,
  );
  const historyAgentName =
    state?.agent.name ?? selectedAgent?.name ?? "Selected Agent";

  async function save() {
    if (selectedId == null || !catalog) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const nextState = await saveAgentPermissionState(
        token,
        selectedId,
        draft,
      );
      setState(nextState);
      const [nextHistory] = await Promise.all([
        getAgentPermissionHistory(token, selectedId),
      ]);
      setHistory(nextHistory.items);
      setMessage(
        "Agent permissions saved. Changes apply on the next protected request.",
      );
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? saveError.message
          : "Could not save Agent permissions.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-[1120px]">
      <PageHeader
        title="Access Control"
        description="Set optional Agent features individually. Investigation ownership and required visit workflows remain enforced for every Agent."
      />
      {error && <InlineAlert>{error}</InlineAlert>}
      {message && (
        <p className="success-message" role="status">
          {message}
        </p>
      )}
      {loading && !catalog ? (
        <Skeleton rows={5} />
      ) : !catalog ? null : agents.length === 0 ? (
        <section className="content-card">
          <h2>No Agent accounts</h2>
          <p className="muted">
            Create an Agent account before configuring feature access.
          </p>
        </section>
      ) : (
        <>
          <section className="mb-6 flex min-w-0 flex-wrap items-center gap-3 rounded-xl border border-openci-border bg-openci-surface p-5 max-[680px]:items-stretch max-[680px]:p-4">
            <label
              className="w-full text-[13px] font-semibold text-openci-text-muted sm:w-auto"
              htmlFor="access-agent"
            >
              Agent
            </label>
            <select
              id="access-agent"
              className="!text-sm min-h-[38px] w-full sm:w-[min(100%,22rem)]"
              value={selectedId ?? ""}
              onChange={(event) => setSelectedId(Number(event.target.value))}
            >
              {agents.map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.name}
                  {agent.is_active ? "" : " · inactive"}
                </option>
              ))}
            </select>
            {selectedAgent && (
              <span
                className={`status-badge max-[680px]:self-start account-${selectedAgent.is_active ? "active" : "inactive"}`}
              >
                {selectedAgent.is_active
                  ? "Active account"
                  : "Inactive account"}
              </span>
            )}
          </section>

          {loading || (state?.agent.id !== selectedId && !error) ? (
            <Skeleton rows={5} />
          ) : (
            state?.agent.id === selectedId && (
              <>
                <section className="mb-6 min-w-0 rounded-xl border border-openci-border bg-openci-surface p-5 max-[680px]:p-4">
                  <div className="mb-4 flex items-start justify-between gap-3 max-[680px]:flex-col max-[680px]:items-stretch">
                    <div>
                      <h2 className="m-0 text-[15px] font-semibold tracking-[-0.015em]">
                        Agent permissions
                      </h2>
                      <p className="mt-[3px] mb-0 text-[13px] text-openci-text-muted">
                        Configure each feature for this Agent. Required
                        workflows remain enforced.
                      </p>
                    </div>
                    <Button
                      className="max-[680px]:self-start"
                      variant="primary"
                      onClick={() => void save()}
                      disabled={saving || !state}
                    >
                      {saving ? "Saving…" : "Save permissions"}
                    </Button>
                  </div>

                  {historyFeature && (
                    <HistoryAccessSection
                      agentId={selectedId ?? 0}
                      agentName={historyAgentName}
                      effectiveAllowed={historyFeature.effective_allowed}
                      selection={historySelection}
                      hasPendingChange={historyHasPendingChange}
                      onSelectionChange={(effect) =>
                        setDraft((current) => ({
                          ...current,
                          [HISTORY_PERMISSION_CODE]: effect,
                        }))
                      }
                    />
                  )}

                  <section
                    className="mt-[18px] border-t border-openci-border pt-4"
                    aria-labelledby="optional-features-heading"
                  >
                    <div className="mb-2 flex items-start justify-between gap-3">
                      <div>
                        <h3 id="optional-features-heading" className="m-0 text-[15px] font-semibold">
                          Optional features
                        </h3>
                        <p className="mt-[3px] mb-0 text-[13px] text-openci-text-muted">
                          Use default follows the Agent role default shown on
                          each feature.
                        </p>
                      </div>
                    </div>
                    <div className="mt-0 grid gap-0">
                      {state.features
                        .filter(
                          (feature) => feature.code !== HISTORY_PERMISSION_CODE,
                        )
                        .map((feature) => {
                          const selectedOverride =
                            draft[feature.code] ?? "inherit";
                          return (
                            <PermissionFeatureRow
                              key={feature.code}
                              feature={feature}
                              selectedOverride={selectedOverride}
                              onOverrideChange={(effect) =>
                                setDraft((current) => ({
                                  ...current,
                                  [feature.code]: effect,
                                }))
                              }
                            />
                          );
                        })}
                    </div>
                  </section>
                </section>

                <RequiredWorkflowsPanel workflows={state.mandatory_workflows} />
                <PermissionHistoryPanel
                  history={history}
                  features={catalog.features}
                />
              </>
            )
          )}
        </>
      )}
    </div>
  );
}
