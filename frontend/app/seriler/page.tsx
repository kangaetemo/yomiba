import type { Metadata } from "next";
import Link from "next/link";
import { JsonLd, breadcrumbs } from "@/components/JsonLd";
import { SeriesRows } from "@/components/SeriesRows";
import { SectionHeading } from "@/components/ui";
import { groupByLetter, publisherPath, publishers } from "@/lib/seriesIndex";
import { SITE_URL, openGraph } from "@/lib/site";
import { getSeriesIndex } from "@/services/catalog";
import type { SeriesIndexItem } from "@/types";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Tüm manga serileri (A–Z)",
  description:
    "Türkiye'de yayımlanan bütün manga serileri alfabetik sırayla: yayınevi, cilt sayısı ve kitapçılardaki en düşük fiyat.",
  alternates: { canonical: "/seriler" },
  openGraph: openGraph({
    title: "Tüm manga serileri (A–Z)",
    description: "Türkiye'de yayımlanan bütün manga serileri, yayınevleri ve en düşük fiyatlarıyla.",
    url: "/seriler",
  }),
};

export default async function SeriesIndexPage() {
  const all = await getSeriesIndex()
    .then((d) => d.series)
    .catch((): SeriesIndexItem[] | null => null);
  const groups = all ? groupByLetter(all) : [];
  const pubs = all ? publishers(all) : [];

  return (
    <div className="space-y-8">
      <JsonLd data={breadcrumbs([{ name: "Yomiba", url: SITE_URL }, { name: "Tüm seriler", url: `${SITE_URL}/seriler` }])} />
      <nav aria-label="Konum" className="text-sm text-muted">
        <Link href="/" className="hover:text-accent">
          ← Ana sayfa
        </Link>
      </nav>
      <SectionHeading
        level={1}
        eyebrow="Katalog"
        title="Tüm seriler"
        lead={
          all
            ? `Türkiye'de yayımlanan ${all.length} manga serisi, alfabetik sırayla. Fiyat, kitapçılarda stokta olan en ucuz cilt.`
            : undefined
        }
      />
      {all === null ? (
        <p className="rounded-xl border border-dashed border-line-strong bg-surface/70 p-6 text-sm text-muted">
          Liste şu an yüklenemedi. Biraz sonra tekrar dene.
        </p>
      ) : (
        <>
          <section aria-labelledby="yayinevleri" className="space-y-3">
            <h2 id="yayinevleri" className="eyebrow">Yayınevleri</h2>
            <ul className="flex flex-wrap gap-2">
              {pubs.map((p) => (
                <li key={p.slug}>
                  <Link
                    href={publisherPath(p.slug)}
                    className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-line bg-surface px-3 text-sm text-ink-2 transition-colors hover:border-line-strong hover:text-accent"
                  >
                    {p.name}
                    <span className="tabular text-faint">{p.count}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>

          <nav aria-label="Harfler" className="border-y border-line py-1">
            <ul className="flex flex-wrap gap-x-1">
              {groups.map(([letter]) => (
                <li key={letter}>
                  <a href={`#harf-${letter}`} className="inline-flex min-h-9 min-w-8 items-center justify-center rounded-md text-sm font-semibold text-ink-2 hover:text-accent">
                    {letter}
                  </a>
                </li>
              ))}
            </ul>
          </nav>

          <div className="space-y-10">
            {groups.map(([letter, items]) => (
              <section key={letter} id={`harf-${letter}`} aria-labelledby={`harf-${letter}-title`} className="scroll-mt-32 space-y-2">
                <h2 id={`harf-${letter}-title`} className="font-display text-3xl font-semibold text-ink">
                  {letter}
                </h2>
                <SeriesRows series={items} />
              </section>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
