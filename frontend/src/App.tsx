import { AppRoutes } from "@/app/router";
import { SessionContext } from "@/app/session";
import { SignInPage } from "@/features/auth/pages/SignInPage";
import { useAuth } from "@/features/auth/hooks/useAuth";
import { ReauthenticationOverlay } from "@/features/auth/components/ReauthenticationOverlay";
import { Skeleton } from "@/components/ui/Primitives";
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

  if (isInitializing) {
    return (
      <main className="login-page">
        <Skeleton rows={3} />
      </main>
    );
  }

  if (!user) return <SignInPage onSignIn={login} />;

  return (
    <SessionContext.Provider key={`${user.id}:${user.role}`} value={{ token: accessToken, user, logout }}>
      <div inert={reauthRequired}>
        <AppRoutes />
      </div>
      {reauthRequired && (
        <ReauthenticationOverlay onReauthenticate={reauthenticate} />
      )}
    </SessionContext.Provider>
  );
}

export default App;
