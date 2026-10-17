"use client";

/**
 * GoogleButton: Google's own "Sign in with Google" button (Google Identity
 * Services). Google hands the browser a signed ID token; the backend checks
 * it (POST /auth/google) and opens a Yomiba session — no Google secret here.
 *
 * Renders nothing without NEXT_PUBLIC_GOOGLE_CLIENT_ID. The script is loaded
 * only on the pages that show the button.
 */

import { useEffect, useRef, useState } from "react";
import { googleLogin, type CurrentUser } from "@/services/auth";

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
  // The latest callback, without re-initializing Google on every render.
  const done = useRef(onSignedIn);
  useEffect(() => {
    done.current = onSignedIn;
  }, [onSignedIn]);

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
            try {
              done.current(await googleLogin(credential));
            } catch (e) {
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
  return (
    <div className="space-y-2">
      {/* Google draws its button here (an iframe); the height keeps the layout still. */}
      <div ref={box} className="flex min-h-11 w-full justify-center" />
      {error && <p role="alert" className="text-center text-sm text-bad">{error}</p>}
    </div>
  );
}

/** True when Google sign-in is configured for this build. */
export const googleEnabled = Boolean(CLIENT_ID);
