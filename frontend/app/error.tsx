"use client";

/**
 * Global error boundary for client-side / server-component rendering errors.
 */

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="space-y-4 py-16 text-center">
      <p className="text-5xl" aria-hidden>
        ⚡
      </p>
      <h1 className="text-2xl font-bold text-ink">Bir şeyler ters gitti</h1>
      <p className="text-sm text-muted">
        Sunucuya şu anda ulaşılamıyor olabilir. Birazdan tekrar deneyin.
        {error.digest && (
          <span className="mt-1 block text-xs text-faint">Hata kodu: {error.digest}</span>
        )}
      </p>
      <button
        onClick={reset}
        className="inline-block rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent hover:bg-accent-hover"
      >
        Tekrar dene
      </button>
    </div>
  );
}
