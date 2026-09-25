/**
 * Thin HTTP layer for the Yomiba API.
 *
 * - In the browser, requests go to the same-origin `/api` prefix and are
 *   proxied to the backend by a Next.js rewrite (see next.config.ts).
 * - In server components, the backend is reached directly via BACKEND_URL.
 */

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
    return process.env.BACKEND_URL || "http://127.0.0.1:8000";
  }
  // Browser: same-origin, proxied by Next.js rewrites.
  return process.env.NEXT_PUBLIC_API_BASE || "/api";
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    cache: "no-store",
    ...init,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body: unknown = await res.json();
      if (body && typeof body === "object" && "detail" in body) {
        const d = (body as { detail: unknown }).detail;
        detail = typeof d === "string" ? d : JSON.stringify(d);
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
