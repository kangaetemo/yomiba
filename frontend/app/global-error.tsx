"use client";

/**
 * Last-resort boundary for errors thrown by the root layout itself
 * (app/error.tsx cannot catch those). Must render its own <html>/<body>.
 */

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="tr">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0a0a0a",
          color: "#e5e5e5",
          fontFamily: "system-ui, sans-serif",
          textAlign: "center",
          padding: "16px",
        }}
      >
        <div>
          <h1 style={{ fontSize: "1.5rem", marginBottom: "0.5rem" }}>
            Yomiba şu anda yanıt vermiyor
          </h1>
          <p style={{ color: "#a3a3a3", fontSize: "0.875rem" }}>
            Kısa süreli bir sorun olabilir. Birazdan tekrar deneyin.
          </p>
          <button
            onClick={reset}
            style={{
              marginTop: "1rem",
              background: "#f97316",
              color: "#0a0a0a",
              border: 0,
              borderRadius: "8px",
              padding: "8px 16px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Tekrar dene
          </button>
        </div>
      </body>
    </html>
  );
}
