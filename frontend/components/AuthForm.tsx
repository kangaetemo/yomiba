"use client";

/**
 * AuthForm: sign in / create an account — with Google (when configured) or
 * e-mail + password. After success the reader goes back where they came
 * from (the ``next`` parameter LoginLink adds), else to the home page.
 */

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { GoogleButton, googleEnabled } from "@/components/GoogleButton";
import { login, register, safeNext } from "@/services/auth";

const input =
  "mt-1 min-h-11 w-full rounded-lg border border-line-strong bg-paper px-3 text-ink placeholder:text-faint focus:border-accent focus:ring-2 focus:ring-accent/30 focus:outline-none";

export function AuthForm({ mode, next }: { mode: "login" | "register"; next?: string }) {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const isLogin = mode === "login";

  function finish() {
    router.replace(safeNext(next) ?? "/");
    router.refresh();
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      const email = String(data.get("email") || "");
      const password = String(data.get("password") || "");
      if (isLogin) await login(email, password);
      else await register(email, password, String(data.get("display_name") || ""));
      finish();
    } catch (err) {
      setError(err instanceof Error ? err.message : "İşlem tamamlanamadı.");
      setBusy(false);
    }
  }

  const other = isLogin ? "/register" : "/login";
  const otherHref = next ? `${other}?next=${encodeURIComponent(next)}` : other;

  return (
    <div className="mx-auto w-full max-w-sm space-y-5 rounded-2xl border border-line bg-surface p-6 shadow-card sm:p-7">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold text-ink">{isLogin ? "Giriş yap" : "Hesap oluştur"}</h1>
        <p className="text-sm text-muted">
          {isLogin
            ? "Koleksiyonun, istek listen ve fiyat alarmların seni bekliyor."
            : "Koleksiyonunu tut, istek listeni oluştur, fiyat düşünce haberin olsun."}
        </p>
      </div>

      {googleEnabled && (
        <>
          <GoogleButton mode={mode} onSignedIn={finish} />
          <div className="flex items-center gap-3 text-xs text-faint">
            <span className="h-px flex-1 bg-line" />
            veya e-postayla
            <span className="h-px flex-1 bg-line" />
          </div>
        </>
      )}

      <form onSubmit={submit} className="space-y-4">
        {!isLogin && (
          <label className="block text-sm font-medium text-ink-2">
            Görünen ad
            <input name="display_name" required maxLength={100} autoComplete="nickname" className={input} />
          </label>
        )}
        <label className="block text-sm font-medium text-ink-2">
          E-posta
          <input name="email" type="email" required autoComplete="email" inputMode="email" className={input} />
        </label>
        <div>
          <label htmlFor="auth-password" className="block text-sm font-medium text-ink-2">
            Parola
          </label>
          <div className="relative">
            <input
              id="auth-password"
              name="password"
              type={showPassword ? "text" : "password"}
              required
              minLength={isLogin ? undefined : 8}
              maxLength={128}
              autoComplete={isLogin ? "current-password" : "new-password"}
              aria-describedby={isLogin ? undefined : "auth-password-hint"}
              className={`${input} pr-20`}
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-pressed={showPassword}
              className="absolute top-1/2 right-1.5 min-h-9 -translate-y-1/2 rounded-md px-2.5 text-xs font-semibold text-muted hover:text-ink"
            >
              {showPassword ? "Gizle" : "Göster"}
            </button>
          </div>
          {!isLogin && (
            <p id="auth-password-hint" className="mt-1 text-xs text-muted">
              En az 8 karakter.
            </p>
          )}
        </div>
        {error && (
          <p role="alert" className="text-sm text-bad">
            {error}
          </p>
        )}
        <button
          disabled={busy}
          className="min-h-11 w-full rounded-lg bg-accent px-4 font-semibold text-on-accent transition-colors hover:bg-accent-hover disabled:opacity-50"
        >
          {busy ? "Bekleyin…" : isLogin ? "Giriş yap" : "Hesap oluştur"}
        </button>
      </form>

      <p className="text-center text-sm text-muted">
        {isLogin ? "Hesabın yok mu?" : "Zaten hesabın var mı?"}{" "}
        <Link href={otherHref} replace className="font-semibold text-ink underline decoration-line-strong underline-offset-4 hover:text-accent">
          {isLogin ? "Kayıt ol" : "Giriş yap"}
        </Link>
      </p>
    </div>
  );
}
