import { useState, type FormEvent } from "react";
import { FormField, InlineAlert } from "@/components/ui/Primitives";
import { Button } from "@/components/ui/button";
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
    <div className="fixed inset-0 z-[4000] grid place-items-center bg-[#122441]/75 p-4">
      <section
        className="w-full max-w-[470px] rounded-2xl border border-[#dce4ef] bg-white p-7 shadow-[0_24px_70px_rgba(8,20,43,0.28)] sm:p-9"
        role="dialog"
        aria-modal="true"
        aria-labelledby="reauth-title"
        aria-describedby="reauth-description"
      >
        <CollectorBrand variant="auth" />
        <h1 id="reauth-title" className="mb-2 text-[27px] font-semibold tracking-[-0.025em] text-[#1b3152]">Sign in to continue</h1>
        <p id="reauth-description" className="mb-7 text-[13px] leading-relaxed text-[#65758f]">
          Your session ended. Sign in to resume this page and any unsaved work.
        </p>
        <form className="grid gap-5" onSubmit={submit}>
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
          <Button className="mt-1 h-11 w-full bg-[#3261c5] text-white hover:bg-[#2853ac]" type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Resume session"}
          </Button>
        </form>
      </section>
    </div>
  );
}
