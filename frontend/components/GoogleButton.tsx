"use client";

/**
 * GoogleButton: Google's own "Sign in with Google" button (Google Identity
 * Services). Google hands the browser a signed ID token; the backend checks
 * it (POST /auth/google) and opens a Yomiba session — no Google secret here.
 *
 * When a password account already uses the address and Google does not own
 * the mailbox (not Gmail / Workspace), the backend asks for proof first: the
 * account's password, or a link mailed to the address (LinkProof).
 *
 * Renders nothing without NEXT_PUBLIC_GOOGLE_CLIENT_ID. The script is loaded
 * only on the pages that show the button.
 */

import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import {
  googleLinkByEmail,
  googleLinkWithPassword,
  googleLogin,
  type CurrentUser,
} from "@/services/auth";

const input =
  "mt-1 min-h-11 w-full rounded-lg border border-line-strong bg-paper px-3 text-ink placeholder:text-faint focus:border-accent focus:ring-2 focus:ring-accent/30 focus:outline-none";
const button =
  "inline-flex min-h-11 w-full items-center justify-center rounded-lg px-4 font-semibold transition-colors disabled:opacity-50";

const SCRIPT_SRC = "https://accounts.google.com/gsi/client";
const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ?? "";

type GoogleId = {
  initialize(options: {
    client_id: string;
    callback: (response: { credential?: string }) => void;
    context?: "signin" | "signup";
    ux_mode?: "popup" | "redirect";
    itp_support?: boolean;
  }): void;
  renderButton(parent: HTMLElement, options: Record<string, string | number>): void;
};

declare global {
  interface Window {
    google?: { accounts: { id: GoogleId } };
  }
}

let loading: Promise<void> | null = null;

function loadScript(): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve();
  loading ??= new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = SCRIPT_SRC;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => {
      loading = null;
      reject(new Error("Google betiği yüklenemedi"));
    };
    document.head.appendChild(script);
  });
  return loading;
}

export function GoogleButton({
  mode,
  onSignedIn,
}: {
  mode: "login" | "register";
  onSignedIn: (user: CurrentUser) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  const [proof, setProof] = useState<{ credential: string; message: string; hasPassword: boolean } | null>(null);
  const [notice, setNotice] = useState<{ user: CurrentUser; text: string } | null>(null);
  // The latest callback, without re-initializing Google on every render.
  const done = useRef(onSignedIn);
  useEffect(() => {
    done.current = onSignedIn;
  }, [onSignedIn]);
  // Signed in: a one-time notice (e.g. "your old password was removed") is
  // shown before moving on.
  const signedIn = useRef((user: CurrentUser) => {
    if (user.notice) setNotice({ user, text: user.notice });
    else done.current(user);
  });

  useEffect(() => {
    if (!CLIENT_ID) return;
    let cancelled = false;
    loadScript()
      .then(() => {
        const id = window.google?.accounts.id;
        if (cancelled || !id || !box.current) return;
        id.initialize({
          client_id: CLIENT_ID,
          context: mode === "register" ? "signup" : "signin",
          ux_mode: "popup",
          itp_support: true,
          callback: async ({ credential }) => {
            if (!credential) return;
            setError("");
            setProof(null);
            try {
              signedIn.current(await googleLogin(credential));
            } catch (e) {
              if (e instanceof ApiError && e.code === "google_link_required") {
                setProof({ credential, message: e.message, hasPassword: e.data?.has_password === true });
                return;
              }
              setError(e instanceof Error ? e.message : "Google ile giriş yapılamadı.");
            }
          },
        });
        const dark = document.documentElement.dataset.theme === "dark";
        id.renderButton(box.current, {
          type: "standard",
          theme: dark ? "filled_black" : "outline",
          size: "large",
          shape: "rectangular",
          text: mode === "register" ? "signup_with" : "continue_with",
          logo_alignment: "center",
          width: Math.min(box.current.clientWidth || 320, 400),
          locale: "tr",
        });
      })
      .catch(() => {
        if (!cancelled) setError("Google girişi şu an yüklenemedi. E-postayla devam edebilirsin.");
      });
    return () => {
      cancelled = true;
    };
  }, [mode]);

  if (!CLIENT_ID) return null;
  if (notice) {
    return (
      <div role="status" className="space-y-3 rounded-lg border border-line bg-paper p-4 text-sm text-ink-2">
        <p>{notice.text}</p>
        <button type="button" onClick={() => done.current(notice.user)} className={`${button} bg-accent text-on-accent hover:bg-accent-hover`}>
          Devam et
        </button>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {/* Google draws its button here (an iframe); the height keeps the layout still. */}
      <div ref={box} className="flex min-h-11 w-full justify-center" />
      {error && <p role="alert" className="text-center text-sm text-bad">{error}</p>}
      {proof && <LinkProof {...proof} onLinked={(user) => signedIn.current(user)} />}
    </div>
  );
}

function LinkProof({
  credential,
  message,
  hasPassword,
  onLinked,
}: {
  credential: string;
  message: string;
  hasPassword: boolean;
  onLinked: (user: CurrentUser) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setStatus(null);
    try {
      await action();
    } catch (e) {
      setStatus({ kind: "error", text: e instanceof Error ? e.message : "İşlem tamamlanamadı." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-line bg-paper p-4 text-sm text-ink-2">
      <p>{message}</p>
      {hasPassword && (
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            const password = String(new FormData(e.currentTarget).get("password") || "");
            void run(async () => onLinked(await googleLinkWithPassword(credential, password)));
          }}
        >
          <label className="block font-medium">
            Yomiba parolan
            <input name="password" type="password" required autoComplete="current-password" className={input} />
          </label>
          <button disabled={busy} className={`${button} bg-accent text-on-accent hover:bg-accent-hover`}>
            Parolayla bağla
          </button>
        </form>
      )}
      <button
        type="button"
        disabled={busy}
        onClick={() =>
          void run(async () => {
            await googleLinkByEmail(credential);
            setStatus({
              kind: "ok",
              text: "Hesabın e-posta adresine bir bağlantı gönderdik. Bağlantıya tıkladıktan sonra yeniden “Google ile devam et” de.",
            });
          })
        }
        className={`${button} border border-line-strong text-ink hover:border-accent`}
      >
        E-postama bağlantı gönder
      </button>
      {status && (
        <p role={status.kind === "error" ? "alert" : "status"} className={status.kind === "error" ? "text-bad" : "text-ok"}>
          {status.text}
        </p>
      )}
    </div>
  );
}

/** True when Google sign-in is configured for this build. */
export const googleEnabled = Boolean(CLIENT_ID);
