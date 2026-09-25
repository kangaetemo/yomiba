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
      <h1 className="text-2xl font-bold text-neutral-50">Bir şeyler ters gitti</h1>
      <p className="text-sm text-neutral-500">
        {error.message || "Beklenmedik bir hata oluştu."}
      </p>
      <button
        onClick={reset}
        className="inline-block rounded-lg bg-orange-500 px-4 py-2 text-sm font-semibold text-neutral-950 hover:bg-orange-400"
      >
        Tekrar dene
      </button>
    </div>
  );
}
