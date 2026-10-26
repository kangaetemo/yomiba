"use client";

/**
 * Admin: the "Yeni seri" Instagram post. Pick a series whose first volume
 * came out lately (or is announced), trim its blurb, download the slides as
 * PNG and copy the caption. No prices or store names, and no Japan/Turkey
 * series status. Nothing is posted anywhere.
 */

import { useState } from "react";
import type { NewSeries } from "@/services/instagram";
import { GROUNDS, NewSeriesSlide, newSeriesTexts, shortBlurb } from "./newSeriesSlides";
import { CaptionEditor, SlideCarousel, useTextEdits, type Slide } from "./parts";
import { CtaSlide, ctaTexts, dayLabel } from "./slides";

const byInterest = (a: NewSeries, b: NewSeries) => b.interest - a.interest || b.release_date.localeCompare(a.release_date);

/** Default pick: the most wanted series that is already out, else the most wanted. */
function defaultPick(series: NewSeries[]): number | null {
  const ranked = [...series].sort(byInterest);
  return (ranked.find((s) => !s.upcoming) ?? ranked[0])?.id ?? null;
}

function hashtag(title: string): string {
  return `#${title.toLocaleLowerCase("tr-TR").replace(/[^\p{L}\p{N}]+/gu, "")}`;
}

function buildCaption(s: NewSeries): string {
  const when = s.upcoming
    ? `İlk cilt ${dayLabel(s.release_date)} tarihinde raflarda olacak.`
    : `İlk cilt ${dayLabel(s.release_date)} itibarıyla raflarda.`;
  const blurb = shortBlurb(s.description);
  return [
    `Yeni seri: ${s.title} 📚`,
    "",
    `${s.publisher} ${s.upcoming ? "yeni bir seriye başlıyor" : "yeni bir seriye başladı"}. ${when}`,
    ...(s.author ? [`Yazar: ${s.author}`] : []),
    ...(blurb ? ["", blurb] : []),
    "",
    "Çıkış tarihleri ve tüm ciltler sitede: yomiba.net (link profilde)",
    "Koleksiyonuna ekle, yeni ciltleri kaçırma 🔖",
    "",
    "Sen bu seriye başlayacak mısın? 👇",
    "",
    ["#manga", "#mangatürkiye", "#yeniseri", hashtag(s.title), "#yomiba"].join(" "),
  ].join("\n");
}

export function NewSeriesStudio({ series }: { series: NewSeries[] }) {
  const [pickedId, setPickedId] = useState(() => defaultPick(series));
  const [ground, setGround] = useState<string>(GROUNDS[0].color);
  const [caption, setCaption] = useState<string | null>(null);
  const texts = useTextEdits();
  const picked = series.find((s) => s.id === pickedId);

  if (!picked) {
    return (
      <p className="rounded-xl border border-line bg-surface p-5 text-sm text-muted">
        Son aylarda başlayan ya da yakında başlayacak seri yok.
      </p>
    );
  }

  const slides: Slide[] = [
    // Keyed by series: each series keeps its own edits.
    texts.slide(`seri-${picked.id}`, picked.title, newSeriesTexts(picked),
      (tx) => <NewSeriesSlide s={picked} tx={tx} ground={ground} page="1 / 2" />),
    texts.slide("cagri", "Çağrı", ctaTexts("Yeni serileri\nkaçırma."), (tx) => <CtaSlide tx={tx} page="2 / 2" />),
  ];

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,440px)_minmax(0,1fr)]">
      <SlideCarousel slides={slides} fileStem={`yomiba-yeni-seri-${picked.slug}`} texts={texts} />

      <div className="space-y-8">
        <CaptionEditor generated={buildCaption(picked)} caption={caption} setCaption={setCaption} rows={16} />

        <section className="space-y-3">
          <h2 className="font-semibold text-ink">Arka plan</h2>
          <div className="flex flex-wrap gap-2">
            {GROUNDS.map((g) => (
              <label key={g.key} className="flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border border-line bg-surface px-3 text-sm font-semibold text-ink-2">
                <input type="radio" name="ig-ground" checked={ground === g.color} onChange={() => setGround(g.color)} className="size-4 accent-accent" />
                <span aria-hidden className="size-5 rounded-full" style={{ background: g.color }} />
                {g.label}
              </label>
            ))}
          </div>
        </section>

        <section className="space-y-3">
          <h2 className="font-semibold text-ink">
            Seri <span className="font-normal text-muted">(ilk cildi son 3 ayda çıkan ya da önümüzdeki 2 ayda çıkacak seriler)</span>
          </h2>
          <ul className="divide-y divide-line rounded-xl border border-line bg-surface">
            {series.map((s) => (
              <li key={s.id}>
                <label className="flex min-h-11 cursor-pointer items-center gap-3 px-3 py-2">
                  <input type="radio" name="ig-series" checked={s.id === pickedId}
                    onChange={() => { setPickedId(s.id); setCaption(null); }} className="size-4 accent-accent" />
                  {s.cover_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={s.cover_url} alt="" className="h-12 w-8 shrink-0 rounded-[3px] object-cover" />
                  ) : <span aria-hidden className="h-12 w-8 shrink-0 rounded-[3px] bg-surface-2" />}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold text-ink">{s.title}</span>
                    <span className="block text-xs text-muted">
                      {s.upcoming ? "Yakında" : "Çıktı"}: {dayLabel(s.release_date)} · {s.publisher}
                      {s.description ? "" : " · tanıtım metni yok"}
                    </span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
