/**
 * Backend base URL for server-side requests and the `/api` rewrite.
 *
 * Trailing slashes are removed so `${base}${path}` never produces `//path`
 * (FastAPI answers `//auth/me` with 404, which used to break every page).
 */
export function backendBaseUrl(): string {
  const raw = process.env.BACKEND_URL || "http://127.0.0.1:8000";
  return raw.trim().replace(/\/+$/, "");
}
