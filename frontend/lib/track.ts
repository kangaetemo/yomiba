/**
 * First-party analytics beacon (POST /api/olay, see backend
 * services/analytics.py). No cookie and no lasting id: the session id lives
 * in this tab's sessionStorage and ends after 30 idle minutes; the only
 * lasting mark is a "visited before" flag. Every call is fire-and-forget.
 */

const SESSION_KEY = "yomiba_oturum";
const SEEN_KEY = "yomiba_gordu";
const IDLE_MS = 30 * 60_000;

type Kind = "pageview" | "outbound" | "search" | "engage";

let firstInSession = false;
let returning = false;
// React dev mode runs effects twice; one address is one view.
let lastView = { u: "", at: 0 };

function sessionId(): string {
  const now = Date.now();
  try {
    const saved = JSON.parse(sessionStorage.getItem(SESSION_KEY) || "null") as { id: string; at: number } | null;
    let id = saved && now - saved.at < IDLE_MS ? saved.id : null;
    if (!id) {
      id = crypto.randomUUID().replace(/-/g, "");
      firstInSession = true;
      try {
        returning = localStorage.getItem(SEEN_KEY) === "1";
        localStorage.setItem(SEEN_KEY, "1");
      } catch {
        // Storage blocked: count as new.
      }
    }
    sessionStorage.setItem(SESSION_KEY, JSON.stringify({ id, at: now }));
    return id;
  } catch {
    firstInSession = true;
    return `t${now.toString(36)}${Math.random().toString(36).slice(2, 10)}`;
  }
}

export function track(kind: Kind, data: { t?: string; q?: string; v?: number; u?: string } = {}): void {
  if (typeof window === "undefined") return;
  try {
    if (kind === "pageview") {
      const u = location.pathname + location.search;
      if (lastView.u === u && Date.now() - lastView.at < 1000) return;
      lastView = { u, at: Date.now() };
    }
    const s = sessionId();
    const payload: Record<string, unknown> = {
      k: kind,
      s,
      u: location.pathname + location.search,
      w: window.innerWidth,
      n: returning,
      ...data,
    };
    // In a single-page app document.referrer stays the landing referrer:
    // send it only with the session's first page view.
    if (kind === "pageview" && firstInSession) {
      payload.r = document.referrer || undefined;
      firstInSession = false;
    }
    const body = JSON.stringify(payload);
    const url = `${(process.env.NEXT_PUBLIC_API_BASE || "/api").replace(/\/+$/, "")}/olay`;
    if (!navigator.sendBeacon?.(url, new Blob([body], { type: "text/plain" }))) {
      void fetch(url, { method: "POST", body, keepalive: true, headers: { "Content-Type": "text/plain" } }).catch(() => {});
    }
  } catch {
    // Analytics never breaks a page.
  }
}
