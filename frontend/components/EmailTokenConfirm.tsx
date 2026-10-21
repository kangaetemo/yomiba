"use client";

/**
 * EmailTokenConfirm: the /eposta-onay page a mailed link opens. Nothing
 * happens until the reader presses a button (mail scanners open links too):
 * verify the address, link the Google account, or — for a verification
 * mail about an account they never opened — delete that account.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  confirmEmailToken,
  emailTokenInfo,
  rejectEmailToken,
  type EmailTokenInfo,
} from "@/services/auth";

const button =
  "inline-flex min-h-11 w-full items-center justify-center rounded-lg px-4 font-semibold transition-colors disabled:opacity-50";
const link = "font-semibold text-ink underline decoration-line-strong underline-offset-4 hover:text-accent";

type State =
  | { step: "loading" }
  | { step: "ask"; info: EmailTokenInfo }
  | { step: "done"; text: string; notice?: string | null; next: { href: string; label: string } }
  | { step: "error"; text: string };

export function EmailTokenConfirm({ token }: { token: string }) {
  const [state, setState] = useState<State>(() =>
    token
      ? { step: "loading" }
      : { step: "error", text: "Bağlantı eksik. E-postadaki bağlantıyı tam olarak açtığından emin ol." },
  );
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) return;
    emailTokenInfo(token)
      .then((info) => setState({ step: "ask", info }))
      .catch((e) => setState({ step: "error", text: e instanceof Error ? e.message : "Bağlantı açılamadı." }));
  }, [token]);

  async function run(action: () => Promise<State>) {
    setBusy(true);
    try {
      setState(await action());
    } catch (e) {
      setState({ step: "error", text: e instanceof Error ? e.message : "İşlem tamamlanamadı." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-sm space-y-5 rounded-2xl border border-line bg-surface p-6 shadow-card sm:p-7">
      <h1 className="text-2xl font-semibold text-ink">E-posta onayı</h1>
      {state.step === "loading" && <p className="text-sm text-muted">Bağlantı kontrol ediliyor…</p>}
      {state.step === "error" && (
        <div className="space-y-3 text-sm">
          <p role="alert" className="text-bad">{state.text}</p>
          <p className="text-muted">
            Yeni bir doğrulama bağlantısını <Link href="/hesap" className={link}>Hesap ayarları</Link> sayfasından isteyebilirsin.
          </p>
        </div>
      )}
      {state.step === "done" && (
        <div role="status" className="space-y-3 text-sm text-ink-2">
          <p className="text-ok">{state.text}</p>
          {state.notice && <p>{state.notice}</p>}
          <Link href={state.next.href} className={link}>{state.next.label}</Link>
        </div>
      )}
      {state.step === "ask" && state.info.purpose === "verify" && (
        <div className="space-y-3 text-sm text-ink-2">
          <p>
            <strong className="break-all">{state.info.email}</strong> adresiyle açılan Yomiba hesabını sen mi açtın?
          </p>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void run(async () => {
                await confirmEmailToken(token);
                return { step: "done", text: "E-posta adresin doğrulandı.", next: { href: "/hesap", label: "Hesap ayarlarına git" } };
              })
            }
            className={`${button} bg-accent text-on-accent hover:bg-accent-hover`}
          >
            Evet, adresimi doğrula
          </button>
          {state.info.can_reject && (
            <>
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    await rejectEmailToken(token);
                    return {
                      step: "done",
                      text: "Hesap silindi. Bu adresle istediğin zaman kendi hesabını açabilirsin.",
                      next: { href: "/register", label: "Hesap oluştur" },
                    };
                  })
                }
                className={`${button} border border-line-strong text-ink hover:border-bad hover:text-bad`}
              >
                Hayır, ben açmadım: hesabı sil
              </button>
              <p className="text-xs text-muted">
                Biri adresini kullanarak hesap açtıysa silmek adresini serbest bırakır. Hesap ve içindeki her şey kalıcı olarak silinir.
              </p>
            </>
          )}
        </div>
      )}
      {state.step === "ask" && state.info.purpose === "google_link" && (
        <div className="space-y-3 text-sm text-ink-2">
          <p>
            Google hesabın <strong className="break-all">{state.info.email}</strong> Yomiba hesabına bağlanacak.
          </p>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void run(async () => {
                const result = await confirmEmailToken(token);
                return {
                  step: "done",
                  text: "Google hesabın bağlandı. Artık “Google ile devam et” ile girebilirsin.",
                  notice: result.notice,
                  next: { href: "/login", label: "Giriş yap" },
                };
              })
            }
            className={`${button} bg-accent text-on-accent hover:bg-accent-hover`}
          >
            Google hesabımı bağla
          </button>
        </div>
      )}
    </div>
  );
}
