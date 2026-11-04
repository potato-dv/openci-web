import { useState, type FormEvent } from "react";
import { Button, FormField, InlineAlert } from "@/components/ui/Primitives";
import { CollectorBrand } from "@/components/layout/CollectorBrand";

type SignInPageProps = {
  onSignIn: (email: string, password: string) => Promise<void>;
};

export function SignInPage({ onSignIn }: SignInPageProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await onSignIn(email, password);
      setPassword("");
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not sign in. Check your details and try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-card">
        <CollectorBrand variant="auth" />
        <h1>Welcome back</h1>
        <p className="login-description">Sign in to your account.</p>
        <form className="login-form" onSubmit={submit}>
          <FormField
            label="Email address"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="username"
            required
          />
          <FormField
            label="Password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
          {error && <InlineAlert>{error}</InlineAlert>}
          <Button variant="primary" type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </section>
    </main>
  );
}
