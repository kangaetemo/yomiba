import Link from "next/link";

export default function NotFound() {
  return (
    <div className="space-y-4 py-16 text-center">
      <p className="text-5xl" aria-hidden>
        📭
      </p>
      <h1 className="text-2xl font-bold text-neutral-50">Sayfa bulunamadı</h1>
      <p className="text-sm text-neutral-500">
        Aradığınız sayfa yok (ya da henüz içe aktarılmamış olabilir).
      </p>
      <Link
        href="/"
        className="inline-block rounded-lg bg-orange-500 px-4 py-2 text-sm font-semibold text-neutral-950 hover:bg-orange-400"
      >
        Aramaya dön
      </Link>
    </div>
  );
}
