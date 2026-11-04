"use client";

/**
 * Admin: the "Tekrar stokta" Instagram carousel. Volumes that came back
 * after selling out everywhere (the site's /tekrar-stokta list): a cover
 * slide, up to three featured volumes with how long they were gone, the
 * list, and a closing slide that points to stock alerts. No prices or store
 * names, so the post does not read as an ad. Nothing is posted anywhere.
 */

import { useState } from "react";
import type { RestockVolume } from "@/services/instagram";
import { CaptionEditor, SlideCarousel, useTextEdits, type Slide } from "./parts";
import { promoTexts } from "./promo";
import {
  RESTOCK_LINK, RESTOCK_LIST_MAX, RestockListSlide, RestockVolumeSlide, gapText, restockListTexts, restockVolumeTexts,
} from "./restockSlides";
import { CoverSlide, CtaSlide, bookTitle, type CoverText, type CtaText } from "./slides";
import type { TextField } from "./parts";
import { CoverPromo } from "./VideoMaker";

const MAX_FEATURED = 3;
const FAN_MAX = 5;

/** Longest gap first (the comeback readers waited for), then interest. */
const byWait = (a: RestockVolume, b: RestockVolume) =>
  (b.out_days ?? 10_000) - (a.out_days ?? 10_000) || b.interest - a.interest || a.id - b.id;
const byInterest = (a: RestockVolume, b: RestockVolume) =>
  b.interest - a.interest || byWait(a, b);

function hashtag(title: string): string {
  return `#${title.toLocaleLowerCase("tr-TR").replace(/[^\p{L}\p{N}]+/gu, "")}`;
}

function buildCaption(volumes: RestockVolume[], featured: RestockVolume[], period: string): string {
  const named = (featured.length ? featured : volumes.slice(0, 3)).map((v) => `${bookTitle(v)} (${gapText(v.out_days)})`);
  const more = volumes.length > named.length ? ` ve ${volumes.length - named.length} cilt daha.` : ".";
  const tags = ["#manga", "#mangatürkiye", "#tekrarstokta",
    ...new Set(featured.map((v) => hashtag(v.series_title))), "#yomiba"];
  return [
    `Tükenen ciltler geri döndü 📚 ${period} ${volumes.length} cilt yeniden raflarda.`,
    `${named.join(", ")}${more}`,
    "",
    "👉 Kaydır: hepsi içeride.",
    "",
    `Tam liste: ${RESTOCK_LINK} (link profilde)`,
    "Beklediğin cilt mi tükendi? Cilt sayfasından stok alarmı kur, stoğa girince haber verelim 🔔",
    "",
    "Sen hangisini bekliyordun? 👇",
    "",
    tags.join(" "),
  ].join("\n");
}

const coverTexts = (total: number, period: string): TextField<CoverText>[] => [
  { id: "etiket", label: "Üst etiket", value: `${period.toLocaleUpperCase("tr-TR")} · STOK TAKİBİ` },
  { id: "baslik", label: "Başlık (son satır renkli)", value: `Tükenmişti.\n${total} cilt\ngeri döndü.`, multiline: true },
  { id: "kaydir", label: "Kaydır düğmesi", value: "Kaydır, hepsini gör" },
];

const ctaTexts = (): TextField<CtaText>[] => [
  { id: "baslik", label: "Başlık", value: "Bir dahakine\nkaçırma.", multiline: true },
  { id: "adim1", label: "1. kutu başlığı", value: "Stok alarmı kur" },
  { id: "adim1Metin", label: "1. kutu metni", value: "Tükenen cilt stoğa girince e-posta gelsin" },
  { id: "adim2", label: "2. kutu başlığı", value: "İstek listene ekle" },
  { id: "adim2Metin", label: "2. kutu metni", value: "Geri döndüğünde sana yazalım" },
  { id: "adim3", label: "3. kutu başlığı", value: "Koleksiyonunu tut" },
  { id: "adim3Metin", label: "3. kutu metni", value: "Eksik ciltlerini tek yerde gör" },
  { id: "linkUst", label: "Link üstü", value: "Link profilde" },
  { id: "link", label: "Link", value: "yomiba.net" },
  { id: "kaydet", label: "Sağ alt düğme", value: "Kaydet, lazım olur" },
];

export function RestockStudio({ volumes, period, fileStem }: {
  volumes: RestockVolume[]; period: string; fileStem: string;
}) {
  const [featuredIds, setFeaturedIds] = useState(() => [...volumes].sort(byInterest).slice(0, MAX_FEATURED).map((v) => v.id));
  const featured = featuredIds.map((id) => volumes.find((v) => v.id === id)).filter((v): v is RestockVolume => !!v);
  const generated = buildCaption(volumes, featured, period);
  const [caption, setCaption] = useState<string | null>(null);
  const texts = useTextEdits();

  const ranked = [...volumes].sort(byInterest);
  const fan = [...featured, ...ranked.filter((v) => !featuredIds.includes(v.id))].slice(0, FAN_MAX);
  const listed = [...ranked.slice(0, RESTOCK_LIST_MAX)].sort(byWait);
  const { slide } = texts;
  const slides: Slide[] = [
    slide("kapak", "Kapak", coverTexts(volumes.length, period), (tx) => <CoverSlide fan={fan} tx={tx} kanji="再入荷" />),
    ...featured.map((v) => {
      const others = ranked.filter((o) => o.id !== v.id);
      return slide(`cilt-${v.id}`, bookTitle(v), restockVolumeTexts(v, others.length),
        (tx) => <RestockVolumeSlide v={v} others={others} tx={tx} />);
    }),
    slide("liste", "Liste", restockListTexts(listed.length, volumes.length, period),
      (tx) => <RestockListSlide volumes={listed} tx={tx} />),
    slide("cagri", "Çağrı", ctaTexts(), (tx) => <CtaSlide tx={tx} />),
  ];

  function toggle(id: number) {
    setCaption(null);
    setFeaturedIds((ids) => ids.includes(id) ? ids.filter((x) => x !== id)
      : ids.length >= MAX_FEATURED ? ids : [...ids, id]);
  }

  if (!volumes.length) {
    return (
      <p className="rounded-xl border border-line bg-surface p-5 text-sm text-muted">
        Bu dönemde tükendikten sonra yeniden stoğa giren cilt yok. Daha uzun bir döneme bakabilirsin.
      </p>
    );
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,440px)_minmax(0,1fr)]">
      <SlideCarousel slides={slides} fileStem={fileStem} texts={texts} />

      <div className="space-y-8">
        <CaptionEditor generated={generated} caption={caption} setCaption={setCaption} />

        <CoverPromo covers={ranked.map((v) => v.cover_url)} fileStem={fileStem} fields={promoTexts(
          `${period.toLocaleUpperCase("tr-TR")} · STOK TAKİBİ`, `Tükenmişti.\n${volumes.length} cilt\ngeri döndü.`,
          "Yeniden stoğa girenler\nsitede.", RESTOCK_LINK,
        )} />

        <section className="space-y-3">
          <h2 className="font-semibold text-ink">
            Öne çıkanlar <span className="font-normal text-muted">({featured.length}/{MAX_FEATURED}, her biri bir cilt sayfası)</span>
          </h2>
          <ul className="divide-y divide-line rounded-xl border border-line bg-surface">
            {[...volumes].sort(byWait).map((v) => {
              const checked = featuredIds.includes(v.id);
              const disabled = !checked && featuredIds.length >= MAX_FEATURED;
              return (
                <li key={v.id}>
                  <label className={`flex min-h-11 items-center gap-3 px-3 py-2 ${disabled ? "opacity-60" : "cursor-pointer"}`}>
                    <input type="checkbox" checked={checked} disabled={disabled} onChange={() => toggle(v.id)} className="size-4 accent-accent" />
                    {v.cover_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={v.cover_url} alt="" className="h-12 w-8 shrink-0 rounded-[3px] object-cover" />
                    ) : <span aria-hidden className="h-12 w-8 shrink-0 rounded-[3px] bg-surface-2" />}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-semibold text-ink">{bookTitle(v)}</span>
                      <span className="block text-xs text-muted">
                        {gapText(v.out_days)} · {v.publisher} · {v.in_stock_offers} mağazada
                      </span>
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        </section>
      </div>
    </div>
  );
}
