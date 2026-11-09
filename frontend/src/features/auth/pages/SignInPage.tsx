import { useState, type FormEvent } from "react";
import { FormField, InlineAlert } from "@/components/ui/Primitives";
import { Button } from "@/components/ui/button";
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
    <main className="grid min-h-dvh place-items-center bg-white px-6 py-12 sm:px-10">
      <section className="w-full max-w-[420px]" aria-labelledby="sign-in-heading">
        <CollectorBrand variant="auth" />
        <h1
          id="sign-in-heading"
          className="mb-2 text-[32px] font-semibold tracking-[-0.03em] text-[#1b3152]"
        >
          Welcome back
        </h1>
        <p className="mb-8 text-[14px] text-[#65758f]">
          Sign in to your account.
        </p>
        <form className="grid gap-5" onSubmit={submit}>
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
          <Button
            className="mt-1 h-11 w-full bg-[#3261c5] text-white hover:bg-[#2853ac]"
            type="submit"
            disabled={busy}
          >
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </section>
    </main>
  );
}
