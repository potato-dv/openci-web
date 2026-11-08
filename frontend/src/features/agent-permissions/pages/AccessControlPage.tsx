import { useEffect, useMemo, useRef, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { WorkspacePanel } from "@/components/layout/WorkspacePanel";
import { WorkspaceSelect } from "@/components/ui/WorkspaceSelect";
import { Button, InlineAlert, Skeleton } from "@/components/ui/Primitives";
import { getUsers } from "@/features/users/api";
import { PermissionFeatureRow } from "@/features/agent-permissions/components/PermissionFeatureRow";
import {
  getAgentPermissionCatalog,
  getAgentPermissionState,
  saveAgentPermissionState,
} from "@/features/agent-permissions/api";
import { useSession } from "@/app/session";
import type {
  AgentFeatureCode,
  AgentPermissionEffect,
  AgentPermissionFeature,
  AgentPermissionState,
  User,
} from "@/types/api";

type PermissionCatalog = {
  features: Omit<AgentPermissionFeature, "override" | "effective_allowed">[];
};

function emptyOverrides(features: PermissionCatalog["features"]) {
  return Object.fromEntries(
    features.map((feature) => [
      feature.code,
      "inherit",
    ]),
  ) as Record<AgentFeatureCode, AgentPermissionEffect>;
}

function permissionDraftFromState(
  state: AgentPermissionState,
  features: PermissionCatalog["features"],
) {
  return {
    ...emptyOverrides(features),
    ...Object.fromEntries(
      state.features.map((feature) => [
        feature.code,
        feature.override ?? "inherit",
      ]),
    ),
  } as Record<AgentFeatureCode, AgentPermissionEffect>;
}

function permissionStateSignature(state: AgentPermissionState | null) {
  return JSON.stringify(
    state?.features
      .map(({ code, override, effective_allowed }) => ({ code, override, effective_allowed }))
      .sort((left, right) => left.code.localeCompare(right.code)) ?? [],
  );
}

function draftMatchesState(
  draft: Record<AgentFeatureCode, AgentPermissionEffect>,
  state: AgentPermissionState,
  features: PermissionCatalog["features"],
) {
  const latest = permissionDraftFromState(state, features);
  return Object.entries(latest).every(
    ([code, effect]) => draft[code as AgentFeatureCode] === effect,
  );
}

export function AccessControlPage() {
  const { token } = useSession();
  const [agents, setAgents] = useState<User[]>([]);
  const [catalog, setCatalog] = useState<PermissionCatalog | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [state, setState] = useState<AgentPermissionState | null>(null);
  const [draft, setDraft] = useState<
    Record<AgentFeatureCode, AgentPermissionEffect>
  >({} as Record<AgentFeatureCode, AgentPermissionEffect>);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [externalChanges, setExternalChanges] = useState(false);
  const lastFreshAtRef = useRef(0);
  const revalidationInFlightRef = useRef(false);

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
        const nextState = await getAgentPermissionState(token, agentId);
        if (cancelled) return;
        setError("");
        setState(nextState);
        setDraft(permissionDraftFromState(nextState, selectedCatalog.features));
        setExternalChanges(false);
        lastFreshAtRef.current = Date.now();
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

  const hasUnsavedChanges = Boolean(
    state && catalog &&
      Object.entries(permissionDraftFromState(state, catalog.features)).some(
        ([code, effect]) => draft[code as AgentFeatureCode] !== effect,
      ),
  );

  useEffect(() => {
    if (!catalog || selectedId == null) return;
    let cancelled = false;

    const refreshIfStale = () => {
      if (
        cancelled ||
        document.visibilityState !== "visible" ||
        revalidationInFlightRef.current ||
        saving ||
        Date.now() - lastFreshAtRef.current < 60_000
      ) return;
      revalidationInFlightRef.current = true;
      const agentId = selectedId;
      void Promise.all([getUsers(token), getAgentPermissionState(token, agentId)])
        .then(([allUsers, nextState]) => {
          if (cancelled) return;
          setAgents(allUsers.filter((item) => item.role === "agent"));
          if (permissionStateSignature(nextState) !== permissionStateSignature(state)) {
            if (hasUnsavedChanges) {
              if (draftMatchesState(draft, nextState, catalog.features)) {
                setState(nextState);
                setDraft(permissionDraftFromState(nextState, catalog.features));
                setExternalChanges(false);
              } else {
                setExternalChanges(true);
              }
            } else {
              setState(nextState);
              setDraft(permissionDraftFromState(nextState, catalog.features));
              setExternalChanges(false);
            }
          }
          setError("");
          lastFreshAtRef.current = Date.now();
        })
        .catch((loadError: unknown) => {
          if (!cancelled) {
            setError(
              loadError instanceof Error
                ? loadError.message
                : "Could not refresh this Agent’s permissions.",
            );
          }
        })
        .finally(() => {
          revalidationInFlightRef.current = false;
        });
    };

    window.addEventListener("focus", refreshIfStale);
    document.addEventListener("visibilitychange", refreshIfStale);
    window.addEventListener("online", refreshIfStale);
    return () => {
      cancelled = true;
      window.removeEventListener("focus", refreshIfStale);
      document.removeEventListener("visibilitychange", refreshIfStale);
      window.removeEventListener("online", refreshIfStale);
    };
  }, [catalog, draft, hasUnsavedChanges, saving, selectedId, state, token]);

  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.id === selectedId),
    [agents, selectedId],
  );
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
      setDraft(permissionDraftFromState(nextState, catalog.features));
      setExternalChanges(false);
      lastFreshAtRef.current = Date.now();
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
    <div className="mx-auto w-full max-w-[1280px]">
      <PageHeader title="Access Control" />
      {error && <InlineAlert>{error}</InlineAlert>}
      {externalChanges && (
        <InlineAlert variant="warning">
          This Agent’s permissions changed elsewhere. Your unsaved selections are preserved. Discard this draft and load the latest permissions before saving.
          <div className="mt-2">
            <Button
              onClick={() => {
                if (selectedId == null || !catalog) return;
                setLoading(true);
                setError("");
                void getAgentPermissionState(token, selectedId)
                  .then((nextState) => {
                    setState(nextState);
                    setDraft(permissionDraftFromState(nextState, catalog.features));
                    setExternalChanges(false);
                    lastFreshAtRef.current = Date.now();
                  })
                  .catch((loadError: unknown) => setError(loadError instanceof Error ? loadError.message : "Could not load the latest permissions."))
                  .finally(() => setLoading(false));
              }}
            >
              Discard draft and load latest
            </Button>
          </div>
        </InlineAlert>
      )}
      {message && (
        <p className="success-message" role="status">
          {message}
        </p>
      )}
      {loading && !catalog ? (
        <Skeleton rows={5} />
      ) : !catalog ? null : agents.length === 0 ? (
        <WorkspacePanel>
          <h2>No Agent accounts</h2>
          <p className="muted">
            Create an Agent account before configuring feature access.
          </p>
        </WorkspacePanel>
      ) : (
        <div className="min-w-0">
          {loading || (state?.agent.id !== selectedId && !error) ? (
            <Skeleton rows={5} />
          ) : (
            state?.agent.id === selectedId && (
              <>
                <WorkspacePanel
                  title="Agent permissions"
                  description="Choose whether this Agent can use each optional feature."
                  className="mb-0"
                  action={
                    <Button
                      className="max-[680px]:self-start"
                      variant="primary"
                      onClick={() => void save()}
                      disabled={saving || !state || externalChanges || !hasUnsavedChanges}
                    >
                      {saving ? "Saving…" : "Save permissions"}
                    </Button>
                  }
                >
                  <div className="mb-5 grid items-end gap-4 border-b border-[#e5eaf2] pb-5 sm:grid-cols-[minmax(0,24rem)_auto] sm:justify-between">
                    <WorkspaceSelect
                      className="w-full"
                      label="Agent"
                      value={String(selectedId ?? "")}
                      onValueChange={(value) => {
                        setExternalChanges(false);
                        setMessage("");
                        setSelectedId(Number(value));
                      }}
                      options={agents.map((agent) => ({ value: String(agent.id), label: `${agent.name}${agent.is_active ? "" : " · inactive"}` }))}
                    />
                    {selectedAgent && (
                      <span className={`status-badge mb-1 account-${selectedAgent.is_active ? "active" : "inactive"}`}>
                        {selectedAgent.is_active ? "Active account" : "Inactive account"}
                      </span>
                    )}
                  </div>

                  <div className="grid gap-0 divide-y divide-[#e5eaf2]">
                    {state.features.map((feature) => (
                      <PermissionFeatureRow
                        key={feature.code}
                        feature={feature}
                        selectedOverride={
                          draft[feature.code] === "inherit"
                            ? (feature.effective_allowed ? "allow" : "deny")
                            : (draft[feature.code] === "deny" ? "deny" : "allow")
                        }
                        hasPendingChange={
                          draft[feature.code] !== (feature.override ?? "inherit")
                        }
                        onOverrideChange={(effect) =>
                          setDraft((current) => ({
                            ...current,
                            [feature.code]: effect,
                          }))
                        }
                      />
                    ))}
                  </div>
                </WorkspacePanel>
              </>
            )
          )}
        </div>
      )}
    </div>
  );
}
