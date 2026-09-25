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

  return <form onSubmit={submit} className="mx-auto max-w-sm space-y-4 rounded-xl border border-neutral-800 bg-neutral-900 p-6">
    <h1 className="text-2xl font-semibold">{mode === "login" ? "Giriş Yap" : "Kayıt Ol"}</h1>
    {mode === "register" && <label className="block text-sm">Görünen ad<input name="display_name" required maxLength={100} className="mt-1 w-full rounded bg-neutral-800 p-2" /></label>}
    <label className="block text-sm">E-posta<input name="email" type="email" required className="mt-1 w-full rounded bg-neutral-800 p-2" /></label>
    <label className="block text-sm">Parola<input name="password" type="password" required minLength={mode === "register" ? 12 : undefined} className="mt-1 w-full rounded bg-neutral-800 p-2" /></label>
    {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
    <button disabled={busy} className="rounded bg-orange-600 px-4 py-2 text-white disabled:opacity-50">{busy ? "Bekleyin…" : mode === "login" ? "Giriş Yap" : "Kayıt Ol"}</button>
  </form>;
}
