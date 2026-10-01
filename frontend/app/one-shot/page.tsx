import type { Metadata } from "next";
import Link from "next/link";
import { SeriesGrid } from "@/components/home/PopularSeries";
import { SectionHeading } from "@/components/ui";
import { getAllOneShots } from "@/services/catalog";
import type { PopularSeries } from "@/types";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "One shot serileri" };

export default async function OneShotPage() {
  const shots = await getAllOneShots()
    .then((d) => d.one_shots)
    .catch((): PopularSeries[] | null => null);

  return (
    <div className="space-y-8">
      <nav aria-label="Konum" className="text-sm text-muted">
        <Link href="/" className="hover:text-accent">
          ← Ana sayfa
        </Link>
      </nav>
      <SectionHeading
        eyebrow="Tek ciltlik hikâyeler"
        title="One shot"
        lead="Tek ciltte başlayıp biten hikâyeler: Japonya'da da Türkiye'de de tamamlanmış, tek cildi olan seriler. Stokta olanlar önce."
      />
      {shots === null ? (
        <p className="rounded-xl border border-dashed border-line-strong bg-surface/70 p-6 text-sm text-muted">
          Liste şu an yüklenemedi. Biraz sonra tekrar dene.
        </p>
      ) : shots.length === 0 ? (
        <p className="rounded-xl border border-dashed border-line-strong bg-surface/70 p-6 text-sm text-muted">
          Henüz listelenecek one shot yok.
        </p>
      ) : (
        <SeriesGrid series={shots} />
      )}
    </div>
  );
}
