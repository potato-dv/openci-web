import { useState, type FormEvent } from "react";
import { FormField, InlineAlert } from "@/components/ui/Primitives";
import { Button } from "@/components/ui/button";
import { CollectorBrand } from "@/components/layout/CollectorBrand";
import { ClipboardList, FileCheck2, Route } from "lucide-react";

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
    <main className="grid min-h-dvh bg-white lg:grid-cols-[minmax(360px,0.9fr)_minmax(480px,1.1fr)]">
      <aside className="hidden min-h-dvh flex-col justify-between bg-[#17345f] p-12 text-white lg:flex xl:p-16">
        <div className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-white text-[#2454ae]"><ClipboardList size={22} /></span><span className="text-lg font-semibold tracking-[-0.02em]">Operational workspace</span></div>
        <div className="max-w-[480px]"><h2 className="mb-5 text-[42px] font-semibold leading-[1.12] tracking-[-0.035em] text-white">Field work, clearly organized.</h2><p className="max-w-[43ch] text-base leading-relaxed text-[#c2d5ef]">Manage investigations, published routes, and report reviews in one operational workspace.</p><div className="mt-9 grid gap-3 text-[13px]"><span className="flex items-center gap-3 rounded-xl border border-white/15 bg-white/5 px-4 py-3"><ClipboardList size={17} /> Investigation records and assignments</span><span className="flex items-center gap-3 rounded-xl border border-white/15 bg-white/5 px-4 py-3"><Route size={17} /> Published field routes</span><span className="flex items-center gap-3 rounded-xl border border-white/15 bg-white/5 px-4 py-3"><FileCheck2 size={17} /> Reports and review</span></div></div>
        <span className="text-xs text-[#9fb6d6]">Collector · Field operations</span>
      </aside>
      <section className="flex min-h-dvh items-center justify-center px-6 py-12 sm:px-10">
        <div className="w-full max-w-[420px]">
        <CollectorBrand variant="auth" />
        <h1 className="mb-2 text-[32px] font-semibold tracking-[-0.03em] text-[#1b3152]">Welcome back</h1>
        <p className="mb-8 text-[14px] text-[#65758f]">Sign in to your account.</p>
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
          <Button className="mt-1 h-11 w-full bg-[#3261c5] text-white hover:bg-[#2853ac]" type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>
        </div>
      </section>
    </main>
  );
}
