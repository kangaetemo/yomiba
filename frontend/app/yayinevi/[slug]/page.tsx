import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { JsonLd, breadcrumbs } from "@/components/JsonLd";
import { SeriesRows } from "@/components/SeriesRows";
import { SectionHeading } from "@/components/ui";
import { TR, publisherPath } from "@/lib/seriesIndex";
import { SITE_URL, metaDescription, openGraph } from "@/lib/site";
import { getSeriesIndex } from "@/services/catalog";

export const dynamic = "force-dynamic";

interface PublisherPageProps {
  params: Promise<{ slug: string }>;
}

async function publisherSeries(slug: string) {
  const { series } = await getSeriesIndex();
  const mine = series.filter((s) => s.publisher_slug === slug).sort((a, b) => TR.compare(a.title, b.title));
  return mine.length > 0 ? { name: mine[0].publisher, series: mine } : null;
}

export async function generateMetadata({ params }: PublisherPageProps): Promise<Metadata> {
  const { slug } = await params;
  const found = await publisherSeries(slug).catch(() => null);
  if (!found) return { title: "Yayınevi bulunamadı" };
  const title = `${found.name} mangaları: seriler ve fiyatlar`;
  const inStock = found.series.filter((s) => s.in_stock_offers > 0).length;
  const description = metaDescription([
    `${found.name} tarafından Türkçe yayımlanan ${found.series.length} manga serisi, ${inStock} tanesi şu an stokta.`,
    "Cilt sayılarını ve kitapçılardaki en düşük fiyatları karşılaştır.",
    "Eksik ciltler için fiyat alarmı kur.",
  ]);
  const url = publisherPath(slug);
  return { title, description, alternates: { canonical: url }, openGraph: openGraph({ title, description, url }) };
}

export default async function PublisherPage({ params }: PublisherPageProps) {
  const { slug } = await params;
  const found = await publisherSeries(slug);
  if (!found) notFound();
  const inStock = found.series.filter((s) => s.in_stock_offers > 0).length;

  return (
    <div className="space-y-8">
      <JsonLd
        data={breadcrumbs([
          { name: "Yomiba", url: SITE_URL },
          { name: "Tüm seriler", url: `${SITE_URL}/seriler` },
          { name: found.name, url: `${SITE_URL}${publisherPath(slug)}` },
        ])}
      />
      <nav aria-label="Konum" className="flex flex-wrap items-center gap-2 text-sm">
        <Link href="/" className="text-muted hover:text-accent">Ana sayfa</Link>
        <span aria-hidden className="text-faint">/</span>
        <Link href="/seriler" className="text-muted hover:text-accent">Tüm seriler</Link>
        <span aria-hidden className="text-faint">/</span>
        <span className="text-ink-2" aria-current="page">{found.name}</span>
      </nav>
      <SectionHeading
        level={1}
        eyebrow="Yayınevi"
        title={`${found.name} mangaları`}
        lead={`${found.name} tarafından yayımlanan ${found.series.length} seri${inStock > 0 ? `; ${inStock} tanesinin en az bir cildi şu an stokta` : ""}.`}
      />
      <SeriesRows series={found.series} showPublisher={false} />
    </div>
  );
}
