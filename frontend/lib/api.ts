/**
 * Thin HTTP layer for the Yomiba API.
 *
 * - In the browser, requests go to the same-origin `/api` prefix and are
 *   proxied to the backend by a Next.js rewrite (see next.config.ts).
 * - In server components, the backend is reached directly via BACKEND_URL.
 */

import { backendBaseUrl } from "@/lib/backendUrl";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function apiBase(): string {
  if (typeof window === "undefined") {
    // Server component: talk to the backend directly.
    return backendBaseUrl();
  }
  // Browser: same-origin, proxied by Next.js rewrites.
  return (process.env.NEXT_PUBLIC_API_BASE || "/api").replace(/\/+$/, "");
}

/** Turn a FastAPI error body into one readable message. 422 validation
 * errors carry a list of `{loc, msg}` objects, not a string. */
function errorDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) =>
        item && typeof item === "object" && "msg" in item
          ? String((item as { msg: unknown }).msg)
          : "",
      )
      .filter(Boolean);
    if (messages.length > 0) return messages.join(" ");
  }
  return fallback;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  let serverHeaders: HeadersInit = {};
  if (typeof window === "undefined") {
    // Only forward the named HttpOnly session cookie from this request. Never
    // pass arbitrary browser headers or expose the token to client JavaScript.
    const { cookies } = await import("next/headers");
    const token = (await cookies()).get("yomiba_session")?.value;
    if (token) serverHeaders = { Cookie: `yomiba_session=${token}` };
  }
  const res = await fetch(`${apiBase()}${path}`, {
    cache: "no-store",
    ...init,
    headers: { ...serverHeaders, ...(init.headers || {}) },
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body: unknown = await res.json();
      if (body && typeof body === "object" && "detail" in body) {
        detail = errorDetail((body as { detail: unknown }).detail, detail);
      }
    } catch {
      // Non-JSON error body; keep the default detail.
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export function getJson<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function patchJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function postJson<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    ...(body !== undefined
      ? {
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : {}),
  });
}

export function putJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function deleteJson<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}
