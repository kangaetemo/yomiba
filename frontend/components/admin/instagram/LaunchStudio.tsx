"use client";

/**
 * Admin: the "site açıldı" announcement carousel. A cover with the catalog
 * counts, one real volume whose price differs between stores, what the site
 * offers, and a closing slide. Pick the example volume, download the slides
 * as PNG and copy the caption. Nothing is posted anywhere.
 */

import { useState } from "react";
import type { InstagramLaunch, LaunchVolume } from "@/services/instagram";
import { FeaturesSlide, LaunchCoverSlide, LaunchCtaSlide, count } from "./launchSlides";
import { CaptionEditor, SlideCarousel, type Slide } from "./parts";
import { CompareSlide, bookTitle, formatPrice } from "./slides";

const FAN_MAX = 5;

const spread = (v: LaunchVolume) => v.offers[v.offers.length - 1].price - v.offers[0].price;

/** Default example: the most wanted of the volumes with a real price gap. */
function defaultExample(examples: LaunchVolume[]): number | null {
  const best = [...examples].sort((a, b) => b.interest - a.interest || spread(b) - spread(a))[0];
  return best?.id ?? null;
}

function buildCaption({ stats }: InstagramLaunch, example: LaunchVolume | undefined): string {
  const swipe = example
    ? `👉 Kaydır: ${bookTitle(example)} ${example.offers.length} mağazada satılıyor ve aradaki fark ${formatPrice(spread(example))}.`
    : "👉 Kaydır: sitede neler olduğunu anlattık.";
  return [
    "yomiba.net açıldı 🎉",
    "",
    `Türkiye'de çıkan mangaların fiyatlarını ${count(stats.stores)} mağazadan toplayıp tek sayfada gösteriyoruz. Şu an ${count(stats.series)} seri, ${count(stats.volumes)} cilt var.`,
    "",
    swipe,
    "",
    "Neler var:",
    "📊 Fiyat karşılaştırma, en ucuz mağaza en üstte",
    "🔔 Fiyat alarmı: hedef fiyatın altına inince e-posta",
    "📅 Yayın takvimi: bu hafta ve bu ay çıkan ciltler",
    "🏷️ İndirimler: fiyatı yeni düşen ciltler",
    "📚 Koleksiyon ve istek listesi",
    "",
    "Ücretsiz, bakmak için üye olmak gerekmiyor. Link profilde: yomiba.net",
    "",
    "Site yeni, eksik seri ya da yanlış fiyat görürsen yorumlara veya DM'e yaz, hemen düzeltelim 🙏",
    "",
    "#manga #mangatürkiye #mangakoleksiyonu #anime #yomiba",
  ].join("\n");
}

export function LaunchStudio({ data }: { data: InstagramLaunch }) {
  const { stats, examples } = data;
  const [exampleId, setExampleId] = useState(() => defaultExample(examples));
  const [caption, setCaption] = useState<string | null>(null);
  const example = examples.find((v) => v.id === exampleId);
  const generated = buildCaption(data, example);

  const ranked = [...examples].sort((a, b) => b.interest - a.interest || spread(b) - spread(a));
  // Covers first: a 読 placeholder in the fan only when nothing else is left.
  const others = ranked.filter((v) => v.id !== exampleId);
  const fan = [...(example ? [example] : []), ...others.filter((v) => v.cover_url), ...others.filter((v) => !v.cover_url)]
    .slice(0, FAN_MAX);
  const total = example ? 4 : 3;
  const page = (n: number) => `${n} / ${total}`;
  const slides: Slide[] = [
    { key: "kapak", label: "Kapak", node: <LaunchCoverSlide fan={fan} stats={stats} page={page(1)} /> },
    ...(example ? [{
      key: "ornek", label: bookTitle(example),
      node: <CompareSlide v={example} others={others} page={page(2)} eyebrow="AYNI CİLT, FARKLI FİYAT"
        meta={`${example.publisher} · ${example.offers.length} mağazada`}
        footerNote={`${count(stats.volumes)} cildin fiyatı sitede`} link="yomiba.net" />,
    }] : []),
    { key: "neler-var", label: "Neler var", node: <FeaturesSlide stats={stats} page={page(total - 1)} /> },
    { key: "cagri", label: "Çağrı", node: <LaunchCtaSlide page={page(total)} /> },
  ];

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,440px)_minmax(0,1fr)]">
      <SlideCarousel slides={slides} fileStem="yomiba-acilis" />

      <div className="space-y-8">
        <CaptionEditor generated={generated} caption={caption} setCaption={setCaption} rows={18} />

        <section className="space-y-3">
          <h2 className="font-semibold text-ink">
            Fiyat örneği <span className="font-normal text-muted">(en az 3 mağazada satılan, fiyat farkı en büyük ciltler)</span>
          </h2>
          <p className="text-sm text-muted">
            Farkı çok büyük olanlarda mağazalar farklı baskıyı (kutu set, özel baskı) aynı cilt sanmış olabilir. Paylaşmadan önce fiyatlara bir bak.
          </p>
          {examples.length ? (
            <ul className="divide-y divide-line rounded-xl border border-line bg-surface">
              {examples.map((v) => (
                <li key={v.id}>
                  <label className="flex min-h-11 cursor-pointer items-center gap-3 px-3 py-2">
                    <input type="radio" name="ig-example" checked={v.id === exampleId}
                      onChange={() => { setExampleId(v.id); setCaption(null); }} className="size-4 accent-accent" />
                    {v.cover_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={v.cover_url} alt="" className="h-12 w-8 shrink-0 rounded-[3px] object-cover" />
                    ) : <span aria-hidden className="h-12 w-8 shrink-0 rounded-[3px] bg-surface-2" />}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-semibold text-ink">{bookTitle(v)}</span>
                      <span className="block text-xs text-muted">
                        {v.offers.length} mağaza, {formatPrice(v.offers[0].price)} - {formatPrice(v.offers[v.offers.length - 1].price)}, fark {formatPrice(spread(v))}
                      </span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          ) : (
            <p className="rounded-xl border border-line bg-surface p-5 text-sm text-muted">
              Şu an 3 ya da daha çok mağazada stokta olan cilt yok; post örnek sayfası olmadan hazırlandı.
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
