"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login, register } from "@/services/auth";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      const email = String(data.get("email") || "");
      const password = String(data.get("password") || "");
      if (mode === "register") {
        await register(email, password, String(data.get("display_name") || ""));
      } else {
        await login(email, password);
      }
      router.push("/");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "İşlem tamamlanamadı.");
    } finally {
      setBusy(false);
    }
  }

  return <form onSubmit={submit} className="mx-auto max-w-sm space-y-4 rounded-xl border border-line bg-surface p-6">
    <h1 className="text-2xl font-bold text-ink">{mode === "login" ? "Giriş Yap" : "Kayıt Ol"}</h1>
    {mode === "register" && <label className="block text-sm text-ink-2">Görünen ad<input name="display_name" required maxLength={100} className="mt-1 w-full rounded-lg border border-line-strong bg-paper px-3 py-2 text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30" /></label>}
    <label className="block text-sm text-ink-2">E-posta<input name="email" type="email" required className="mt-1 w-full rounded-lg border border-line-strong bg-paper px-3 py-2 text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30" /></label>
    <label className="block text-sm text-ink-2">Parola<input name="password" type="password" required minLength={mode === "register" ? 12 : undefined} className="mt-1 w-full rounded-lg border border-line-strong bg-paper px-3 py-2 text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30" /></label>
    {error && <p role="alert" className="text-sm text-bad">{error}</p>}
    <button disabled={busy} className="w-full rounded-lg bg-accent px-4 py-2 font-semibold text-on-accent transition-colors hover:bg-accent-hover disabled:opacity-50">{busy ? "Bekleyin…" : mode === "login" ? "Giriş Yap" : "Kayıt Ol"}</button>
  </form>;
}
