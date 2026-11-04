import { useState, type FormEvent } from "react";
import { Button, FormField, InlineAlert } from "@/components/ui/Primitives";
import { CollectorBrand } from "@/components/layout/CollectorBrand";

type Props = {
  onReauthenticate: (email: string, password: string) => Promise<void>;
};

export function ReauthenticationOverlay({ onReauthenticate }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await onReauthenticate(email, password);
      setPassword("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not sign in. Check your details and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="reauth-backdrop">
      <section
        className="reauth-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="reauth-title"
        aria-describedby="reauth-description"
      >
        <CollectorBrand variant="auth" />
        <h1 id="reauth-title">Sign in to continue</h1>
        <p id="reauth-description" className="login-description">
          Your session ended. Sign in to resume this page and any unsaved work.
        </p>
        <form className="login-form" onSubmit={submit}>
          <FormField
            label="Email address"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="username"
            autoFocus
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
            {busy ? "Signing in…" : "Resume session"}
          </Button>
        </form>
      </section>
    </div>
  );
}
