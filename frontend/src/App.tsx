import { AppRoutes } from "@/app/router";
import { SessionContext } from "@/app/session";
import { SignInPage } from "@/features/auth/pages/SignInPage";
import { useAuth } from "@/features/auth/hooks/useAuth";
import { Skeleton } from "@/components/ui/Primitives";
import "./App.css";

function App() {
  const { accessToken, user, isInitializing, login, logout } = useAuth();

  if (isInitializing) {
    return (
      <main className="login-page">
        <Skeleton rows={3} />
      </main>
    );
  }

  if (!user) return <SignInPage onSignIn={login} />;

  return (
    <SessionContext.Provider value={{ token: accessToken, user, logout }}>
      <AppRoutes />
    </SessionContext.Provider>
  );
}

export default App;
