import { SearchSection } from "@/components/SearchSection";

export default function HomePage() {
  return (
    <div className="space-y-10">
      <section className="space-y-4 pt-6 text-center sm:pt-12">
        <h1 className="text-4xl font-bold tracking-tight text-neutral-50 sm:text-5xl">
          Manga fiyatları, <span className="text-orange-500">karşılaştırıldı</span>.
        </h1>
        <p className="mx-auto max-w-xl text-base text-neutral-400">
          Yomiba aynı manga cildinin fiyatını BKM Kitap, D&R, Amazon, Gerekli
          Şeyler ve daha fazla mağazada karşılaştırır — böylece her zaman en
          ucuzundan alırsınız.
        </p>
      </section>

      <SearchSection />

      <section className="rounded-xl border border-neutral-800 bg-neutral-900/50 p-4 text-sm text-neutral-500">
        <p>
          Takip edilen mağazalar:{" "}
          <span className="text-neutral-300">BKM Kitap</span> ·{" "}
          <span className="text-neutral-300">D&amp;R</span> ·{" "}
          <span className="text-neutral-300">Amazon</span> ·{" "}
          <span className="text-neutral-300">Gerekli Şeyler</span> ·{" "}
          <span className="text-neutral-300">Kitap Sepeti</span> ·{" "}
          <span className="text-neutral-300">Kitapbulan</span> ·{" "}
          <span className="text-neutral-300">Kitapsec</span> ·{" "}
          <span className="text-neutral-300">Cizman</span> ·{" "}
          <span className="text-neutral-300">Komikşeyler</span>. Yeni
          mağazalar yolda.
        </p>
      </section>
    </div>
  );
}
