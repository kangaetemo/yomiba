import { SearchSection } from "@/components/SearchSection";
import { DropsSection } from "@/components/DropsSection";

const STORES = [
  "BKM Kitap",
  "Gerekli Şeyler",
  "Kitap Sepeti",
  "Kitapbulan",
  "Kitapsec",
  "Komikşeyler",
  "Edessa Kitabevi",
];

export default async function HomePage() {
  return (
    <div className="space-y-10">
      <section className="relative space-y-4 pt-6 text-center sm:pt-12">
        <div
          aria-hidden
          className="screentone pointer-events-none absolute inset-x-0 top-0 -z-10 mx-auto h-40 max-w-md [mask-image:radial-gradient(closest-side,black,transparent)]"
        />
        <h1 className="text-4xl font-extrabold text-ink sm:text-6xl">
          Manga fiyatları,{" "}
          <span className="relative whitespace-nowrap text-accent">
            karşılaştırıldı
            <svg
              aria-hidden
              viewBox="0 0 200 12"
              preserveAspectRatio="none"
              className="absolute -bottom-2 left-0 h-3 w-full text-accent/40"
            >
              <path
                d="M2 9 Q 50 2 100 7 T 198 5"
                fill="none"
                stroke="currentColor"
                strokeWidth="3"
                strokeLinecap="round"
              />
            </svg>
          </span>
          .
        </h1>
        <p className="mx-auto max-w-xl text-base text-muted sm:text-lg">
          Aynı cildin fiyatını {STORES.length} mağazada yan yana gör, stokta
          olanı ve en ucuzunu tek bakışta bul.
        </p>
      </section>

      <SearchSection />

      <DropsSection />

      <section className="rounded-xl border border-line bg-surface p-4 text-sm">
        <p className="mb-2 text-xs font-semibold tracking-wide text-muted uppercase">
          Takip edilen mağazalar
        </p>
        <ul className="flex flex-wrap gap-2">
          {STORES.map((store) => (
            <li
              key={store}
              className="rounded-full border border-line bg-paper px-3 py-1 text-ink-2"
            >
              {store}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
