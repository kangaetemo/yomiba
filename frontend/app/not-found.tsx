import Link from "next/link";

export default function NotFound() {
  return (
    <div className="space-y-4 py-16 text-center">
      <p className="text-5xl" aria-hidden>
        📭
      </p>
      <h1 className="text-2xl font-bold text-ink">Sayfa bulunamadı</h1>
      <p className="text-sm text-muted">
        Aradığınız sayfa yok (ya da henüz içe aktarılmamış olabilir).
      </p>
      <Link
        href="/"
        className="inline-block rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent hover:bg-accent-hover"
      >
        Aramaya dön
      </Link>
    </div>
  );
}
