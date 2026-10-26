"use client";

/**
 * Admin: the "Yeni seri" Instagram post. Pick a series whose first volume
 * came out lately (or is announced), trim its blurb, download the slides as
 * PNG and copy the caption. No prices or store names, and no Japan/Turkey
 * series status. Nothing is posted anywhere.
 */

import { useEffect, useState } from "react";
import type { NewSeries } from "@/services/instagram";
import { coverPalettes, type Palette } from "./coverColors";
import { NewSeriesSlide, PALETTES, newSeriesTexts, shortBlurb } from "./newSeriesSlides";
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
  const [paletteKey, setPaletteKey] = useState("kapak");
  const [caption, setCaption] = useState<string | null>(null);
  const texts = useTextEdits();
  const picked = series.find((s) => s.id === pickedId);

  // Colors from the picked cover, worked out in the browser.
  const coverUrl = picked?.cover_url ?? null;
  const [fromCover, setFromCover] = useState<{ url: string; palettes: Awaited<ReturnType<typeof coverPalettes>> } | null>(null);
  useEffect(() => {
    if (!coverUrl) return;
    let live = true;
    coverPalettes(coverUrl).then((palettes) => { if (live) setFromCover({ url: coverUrl, palettes }); });
    return () => { live = false; };
  }, [coverUrl]);
  const cover = fromCover?.url === coverUrl ? fromCover.palettes : null;
  const choices: { key: string; label: string; palette: Palette }[] = [
    ...(cover ? [
      { key: "kapak", label: "Kapaktan, uyumlu", palette: cover.match },
      { key: "kapak-zit", label: "Kapaktan, zıt", palette: cover.contrast },
    ] : []),
    ...PALETTES,
  ];
  const chosen = choices.find((c) => c.key === paletteKey) ?? choices[0];

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
      (tx) => <NewSeriesSlide s={picked} tx={tx} palette={chosen.palette} page="1 / 2" />),
    texts.slide("cagri", "Çağrı", ctaTexts("Yeni serileri\nkaçırma."), (tx) => <CtaSlide tx={tx} page="2 / 2" />),
  ];

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,440px)_minmax(0,1fr)]">
      <SlideCarousel slides={slides} fileStem={`yomiba-yeni-seri-${picked.slug}`} texts={texts} />

      <div className="space-y-8">
        <CaptionEditor generated={buildCaption(picked)} caption={caption} setCaption={setCaption} rows={16} />

        <section className="space-y-3">
          <h2 className="font-semibold text-ink">Renkler <span className="font-normal text-muted">(arka plan ve rozet)</span></h2>
          <div className="flex flex-wrap gap-2">
            {choices.map((c) => (
              <label key={c.key} className="flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border border-line bg-surface px-3 text-sm font-semibold text-ink-2">
                <input type="radio" name="ig-ground" checked={chosen.key === c.key} onChange={() => setPaletteKey(c.key)} className="size-4 accent-accent" />
                <span aria-hidden className="flex">
                  <span className="size-5 rounded-full" style={{ background: c.palette.ground }} />
                  <span className="-ml-1.5 size-5 rounded-full ring-2 ring-surface" style={{ background: c.palette.accent }} />
                </span>
                {c.label}
              </label>
            ))}
          </div>
          {coverUrl && !cover ? (
            <p className="text-xs text-muted">{fromCover?.url === coverUrl ? "Bu kapaktan renk çıkarılamadı." : "Kapağın renkleri hesaplanıyor…"}</p>
          ) : null}
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
