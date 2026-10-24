"use client";

/**
 * Admin: the weekly "Bu hafta çıkanlar" Instagram carousel from real catalog
 * data. Pick up to three volumes to feature (each gets a store-by-store
 * price slide), swipe through the preview, download the slides as PNG and
 * copy the caption. Nothing is posted anywhere.
 */

import { useState } from "react";
import type { InstagramVolume } from "@/services/instagram";
import { CaptionEditor, SlideCarousel, type Slide } from "./parts";
import {
  CompareSlide, CoverSlide, CtaSlide, LIST_MAX, ListSlide, bookTitle, dayLabel, formatPrice,
} from "./slides";

const MAX_FEATURED = 3;
const FAN_MAX = 5;

const byInterest = (a: InstagramVolume, b: InstagramVolume) =>
  b.interest - a.interest || b.offers.length - a.offers.length || a.id - b.id;

/** Default picks: the most wanted volumes that two or more stores sell. */
function defaultFeatured(volumes: InstagramVolume[]): number[] {
  const priced = volumes.filter((v) => v.offers.length >= 2).sort(byInterest);
  const rest = volumes.filter((v) => v.offers.length === 1).sort(byInterest);
  return [...priced, ...rest].slice(0, MAX_FEATURED).map((v) => v.id);
}

function hashtag(title: string): string {
  return `#${title.toLocaleLowerCase("tr-TR").replace(/[^\p{L}\p{N}]+/gu, "")}`;
}

function buildCaption(volumes: InstagramVolume[], featured: InstagramVolume[]): string {
  const named = (featured.length ? featured : volumes.slice(0, 3)).map(bookTitle);
  const more = volumes.length > named.length ? " ve daha fazlası." : ".";
  const spread = featured.find((v) => v.offers.length >= 2);
  const swipe = spread
    ? `👉 Kaydır: ${bookTitle(spread)} mağazalar arasında ${formatPrice(spread.offers[spread.offers.length - 1].price - spread.offers[0].price)} fark ediyor.`
    : "👉 Kaydır: haftanın tam listesi ve en ucuz mağazalar içeride.";
  const tags = ["#manga", "#mangatürkiye", "#yenimanga",
    ...new Set(featured.map((v) => hashtag(v.series_title))), "#yomiba"];
  return [
    `Bu hafta raflara ${volumes.length} yeni cilt geldi 📚`,
    `${named.join(", ")}${more}`,
    "",
    swipe,
    "",
    "Hepsinin güncel fiyatı: yomiba.net/takvim (link profilde)",
    "Bu postu kaydet, alışverişe çıkmadan bak 🔖",
    "",
    "Sen hangisini alıyorsun? 👇",
    "",
    tags.join(" "),
  ].join("\n");
}

export function InstagramStudio({ volumes, weekLabel, fileStem }: {
  volumes: InstagramVolume[]; weekLabel: string; fileStem: string;
}) {
  const [featuredIds, setFeaturedIds] = useState(() => defaultFeatured(volumes));
  const featured = featuredIds.map((id) => volumes.find((v) => v.id === id)).filter((v): v is InstagramVolume => !!v);
  const generated = buildCaption(volumes, featured);
  const [caption, setCaption] = useState<string | null>(null);

  const ranked = [...volumes].sort(byInterest);
  const fan = [...featured, ...ranked.filter((v) => !featuredIds.includes(v.id))].slice(0, FAN_MAX);
  const listed = (volumes.length > LIST_MAX ? ranked.slice(0, LIST_MAX) : [...volumes])
    .sort((a, b) => a.release_date.localeCompare(b.release_date) || a.id - b.id);
  const total = featured.length + 3;
  const page = (n: number) => `${n} / ${total}`;
  const slides: Slide[] = [
    { key: "kapak", label: "Kapak", node: <CoverSlide fan={fan} total={volumes.length} weekLabel={weekLabel} page={page(1)} /> },
    ...featured.map((v, i) => ({
      key: `cilt-${v.id}`, label: bookTitle(v),
      node: <CompareSlide v={v} others={ranked.filter((o) => o.id !== v.id)} page={page(i + 2)} />,
    })),
    { key: "liste", label: "Liste", node: <ListSlide volumes={listed} total={volumes.length} weekLabel={weekLabel} page={page(featured.length + 2)} /> },
    { key: "cagri", label: "Çağrı", node: <CtaSlide page={page(total)} /> },
  ];

  function toggle(id: number) {
    setCaption(null);
    setFeaturedIds((ids) => ids.includes(id) ? ids.filter((x) => x !== id)
      : ids.length >= MAX_FEATURED ? ids : [...ids, id]);
  }

  if (!volumes.length) {
    return (
      <p className="rounded-xl border border-line bg-surface p-5 text-sm text-muted">
        Bu hafta için katalogda çıkış tarihi olan cilt yok. Başka bir haftaya bakabilirsin.
      </p>
    );
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,440px)_minmax(0,1fr)]">
      <SlideCarousel slides={slides} fileStem={fileStem} />

      <div className="space-y-8">
        <CaptionEditor generated={generated} caption={caption} setCaption={setCaption} />

        <section className="space-y-3">
          <h2 className="font-semibold text-ink">
            Öne çıkanlar <span className="font-normal text-muted">({featured.length}/{MAX_FEATURED}, her biri bir fiyat sayfası)</span>
          </h2>
          <ul className="divide-y divide-line rounded-xl border border-line bg-surface">
            {[...volumes].sort((a, b) => a.release_date.localeCompare(b.release_date) || a.id - b.id).map((v) => {
              const checked = featuredIds.includes(v.id);
              const disabled = !checked && (featuredIds.length >= MAX_FEATURED || v.offers.length === 0);
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
                        {dayLabel(v.release_date)} · {v.offers.length ? `${v.offers.length} mağaza, en ucuz ${formatPrice(v.offers[0].price)}` : "stokta değil"}
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
