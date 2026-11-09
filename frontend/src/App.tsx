import { useCallback, useEffect, useState } from "react";
import { AppRoutes } from "@/app/router";
import { SessionContext } from "@/app/session";
import { SignInPage } from "@/features/auth/pages/SignInPage";
import { useAuth } from "@/features/auth/hooks/useAuth";
import { ReauthenticationOverlay } from "@/features/auth/components/ReauthenticationOverlay";
import { Skeleton } from "@/components/ui/Primitives";
import { getMyAgentPermissions } from "@/features/agent-permissions/api";
import type { AgentPermissions } from "@/types/api";
import { RealtimeProvider } from "@/realtime/RealtimeProvider";
import "./App.css";

function App() {
  const {
    accessToken,
    user,
    isInitializing,
    reauthRequired,
    login,
    reauthenticate,
    logout,
  } = useAuth();
  const [permissionState, setPermissionState] = useState<{ userId: number; permissions: AgentPermissions } | null>(null);

  const refreshAgentPermissions = useCallback(async () => {
    const currentUser = user;
    if (currentUser?.role !== "agent" || !accessToken) return;
    try {
      const response = await getMyAgentPermissions(accessToken);
      setPermissionState({ userId: currentUser.id, permissions: response.permissions });
    } catch {
      // Keep the current/default UI state; protected API calls remain authoritative.
    }
  }, [accessToken, user]);

  useEffect(() => {
    const currentUser = user;
    if (currentUser?.role !== "agent" || !accessToken) return;
    const agentId = currentUser.id;
    const token = accessToken;
    let cancelled = false;
    async function loadPermissions() {
      try {
        const response = await getMyAgentPermissions(token);
        if (!cancelled) setPermissionState({ userId: agentId, permissions: response.permissions });
      } catch {
        // Keep the current/default UI state; protected API calls remain authoritative.
      }
    }
    void loadPermissions();
    return () => { cancelled = true; };
  }, [accessToken, user]);

  if (isInitializing) {
    return (
      <main className="login-page">
        <Skeleton rows={3} />
      </main>
    );
  }

  if (!user) return <SignInPage onSignIn={login} />;

  return (
    <SessionContext.Provider
      key={`${user.id}:${user.role}`}
      value={{
        token: accessToken,
        user,
        logout,
        agentPermissions: permissionState?.userId === user.id ? permissionState.permissions : null,
        refreshAgentPermissions,
      }}
    >
      <RealtimeProvider
        token={accessToken}
        userId={user.id}
        role={user.role}
        enabled={!reauthRequired}
        onPermissionsChanged={refreshAgentPermissions}
      >
        <div inert={reauthRequired}>
          <AppRoutes />
        </div>
        {reauthRequired && (
          <ReauthenticationOverlay onReauthenticate={reauthenticate} />
        )}
      </RealtimeProvider>
    </SessionContext.Provider>
  );
}

export default App;
