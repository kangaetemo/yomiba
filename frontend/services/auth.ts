import { ApiError, getJson, patchJson, postJson } from "@/lib/api";
import { unstable_rethrow } from "next/navigation";
import { cache } from "react";

export type CurrentUser = {
  id: number;
  email: string;
  display_name: string;
  role: "USER" | "ADMIN";
  /** False for an account opened with Google that never set a password. */
  has_password: boolean;
  /** A Google account is linked. */
  google: boolean;
  /** The owner proved the address (a mailed link, or Gmail / Workspace Google). */
  email_verified: boolean;
  /** Something to tell the reader once (e.g. the old password was removed). */
  notice?: string | null;
};

export type EmailTokenInfo = {
  purpose: "verify" | "google_link";
  email: string;
  /** "Ben açmadım" may delete this (unverified) account. */
  can_reject: boolean;
};

export const getMe = () => getJson<CurrentUser>("/auth/me");
export const login = (email: string, password: string) =>
  postJson<CurrentUser>("/auth/login", { email, password });
export const register = (email: string, password: string, display_name: string) =>
  postJson<CurrentUser>("/auth/register", { email, password, display_name });
/** "Sign in with Google": the ID token Google gave the browser. */
export const googleLogin = (credential: string) =>
  postJson<CurrentUser>("/auth/google", { credential });
/** Link Google to the existing account with that e-mail, proved by its password. */
export const googleLinkWithPassword = (credential: string, password: string) =>
  postJson<CurrentUser>("/auth/google/link", { credential, password });
/** …or by a link mailed to the address. */
export const googleLinkByEmail = (credential: string) =>
  postJson<{ sent: boolean }>("/auth/google/link-email", { credential });
export const sendVerification = () => postJson<{ sent: boolean }>("/auth/verify-email/send");
export const emailTokenInfo = (token: string) => postJson<EmailTokenInfo>("/auth/email-token", { token });
export const confirmEmailToken = (token: string) =>
  postJson<{ purpose: EmailTokenInfo["purpose"]; email: string; notice: string | null }>(
    "/auth/email-token/confirm",
    { token },
  );
export const rejectEmailToken = (token: string) => postJson<void>("/auth/email-token/reject", { token });
export const updateProfile = (display_name: string) =>
  patchJson<CurrentUser>("/auth/me", { display_name });
/** Change (or, on a Google-only account, set) the password; other devices are signed out. */
export const changePassword = (current_password: string, new_password: string) =>
  postJson<CurrentUser>("/auth/password", { current_password, new_password });
export const logoutOthers = () => postJson<{ revoked: number }>("/auth/logout-others");
/** ``confirm``: the password, or the e-mail on a Google-only account. */
export const deleteAccount = (confirm: string) => postJson<void>("/auth/delete", { confirm });

/** Where to go after signing in: a same-site path only (never "//evil"). */
export function safeNext(raw: string | null | undefined): string | null {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/\\")) return null;
  if (/^\/(login|register)(\/|\?|$)/.test(raw)) return null;
  return raw;
}

/**
 * Current user for chrome (header) rendering. When the backend
 * is unreachable or answers with an unexpected error, the page renders as
 * logged out instead of the whole site failing with a 500. Next.js rendering
 * control signals still propagate to the framework. Memoised per request:
 * the layout and the page both ask, the backend is called once.
 */
export const currentUserOrNull = cache(async (): Promise<CurrentUser | null> => {
  try {
    return await currentUser();
  } catch (error) {
    unstable_rethrow(error);
    console.error("currentUser failed; rendering as anonymous", error);
    return null;
  }
});

export async function currentUser(): Promise<CurrentUser | null> {
  try {
    return await getMe();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}
