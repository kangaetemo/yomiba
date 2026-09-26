import type { NextConfig } from "next";

/**
 * The frontend talks to the FastAPI backend in two ways:
 *
 *  1. Client components call the same-origin `/api/*` path; Next.js rewrites
 *     proxy those requests to the backend server-side. This works from any
 *     origin (local dev or hosted preview) without CORS configuration.
 *
 *  2. Server components fetch the backend directly using BACKEND_URL
 *     (reachable from the Node process).
 */
/**
 * Preview host (derived, not hard-coded): the live preview is served under
 * `https://3000-<sandboxId>.e2b.app` where `<sandboxId>` is the E2B sandbox
 * id (env var `E2B_SANDBOX_ID`). The sandbox — and therefore the host — can
 * change between restarts, so derive it at dev-server startup. Next 16
 * requires plain strings (no wildcards) in `allowedDevOrigins`.
 */
const allowedDevOrigins: string[] = [];
const sandboxId = process.env.E2B_SANDBOX_ID;
if (sandboxId) {
  allowedDevOrigins.push(`3000-${sandboxId}.e2b.app`);
}

const nextConfig: NextConfig = {
  // The live preview is served under a host like
  // https://3000-<sandboxId>.e2b.app. Next 16 blocks cross-origin dev
  // resource requests (HMR/dev chunks) from origins it does not know,
  // which would leave the page unhydrated in the preview — allow the
  // preview origin so client components (search, etc.) stay functional.
  allowedDevOrigins,
  async rewrites() {
    // Trailing slash stripped: "https://api.example/" must not yield "//path".
    const backend = (process.env.BACKEND_URL || "http://127.0.0.1:8000")
      .trim()
      .replace(/\/+$/, "");
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/:path*`,
      },
    ];
  },
};

export default nextConfig;
