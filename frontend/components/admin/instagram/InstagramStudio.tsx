"use client";

/**
 * Admin: the weekly "Bu hafta çıkanlar" Instagram carousel from real catalog
 * data. Pick up to three volumes to feature (each gets a store-by-store
 * price slide), swipe through the preview, download the slides as PNG and
 * copy the caption. Nothing is posted anywhere.
 */

import { toBlob } from "html-to-image";
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { InstagramVolume } from "@/services/instagram";
import {
  CompareSlide, CoverSlide, CtaSlide, LIST_MAX, ListSlide, SLIDE_H, SLIDE_W, bookTitle, dayLabel, formatPrice,
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

/** A slide drawn at full size and scaled to its box's width. */
function ScaledSlide({ children, slideRef }: { children: ReactNode; slideRef: (node: HTMLDivElement | null) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.4);
  useEffect(() => {
    const node = box.current;
    if (!node) return;
    const update = () => setScale(node.clientWidth / SLIDE_W);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return (
    <div ref={box} className="relative aspect-[4/5] w-full overflow-hidden">
      <div style={{ position: "absolute", left: 0, top: 0, transformOrigin: "0 0", transform: `scale(${scale})` }}>
        <div ref={slideRef} style={{ width: SLIDE_W, height: SLIDE_H }}>{children}</div>
      </div>
    </div>
  );
}

export function InstagramStudio({ volumes, weekLabel, fileStem }: {
  volumes: InstagramVolume[]; weekLabel: string; fileStem: string;
}) {
  const [featuredIds, setFeaturedIds] = useState(() => defaultFeatured(volumes));
  const featured = featuredIds.map((id) => volumes.find((v) => v.id === id)).filter((v): v is InstagramVolume => !!v);
  const generated = buildCaption(volumes, featured);
  const [caption, setCaption] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [index, setIndex] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const track = useRef<HTMLDivElement>(null);
  const slideNodes = useRef<(HTMLDivElement | null)[]>([]);

  const ranked = [...volumes].sort(byInterest);
  const fan = [...featured, ...ranked.filter((v) => !featuredIds.includes(v.id))].slice(0, FAN_MAX);
  const listed = (volumes.length > LIST_MAX ? ranked.slice(0, LIST_MAX) : [...volumes])
    .sort((a, b) => a.release_date.localeCompare(b.release_date) || a.id - b.id);
  const total = featured.length + 3;
  const page = (n: number) => `${n} / ${total}`;
  const slides: { key: string; label: string; node: ReactNode }[] = [
    { key: "kapak", label: "Kapak", node: <CoverSlide fan={fan} total={volumes.length} weekLabel={weekLabel} page={page(1)} /> },
    ...featured.map((v, i) => ({
      key: `cilt-${v.id}`, label: bookTitle(v),
      node: <CompareSlide v={v} others={ranked.filter((o) => o.id !== v.id)} page={page(i + 2)} />,
    })),
    { key: "liste", label: "Liste", node: <ListSlide volumes={listed} total={volumes.length} weekLabel={weekLabel} page={page(featured.length + 2)} /> },
    { key: "cagri", label: "Çağrı", node: <CtaSlide page={page(total)} /> },
  ];
  const current = Math.min(index, slides.length - 1);

  function toggle(id: number) {
    setCaption(null);
    setFeaturedIds((ids) => ids.includes(id) ? ids.filter((x) => x !== id)
      : ids.length >= MAX_FEATURED ? ids : [...ids, id]);
  }

  function go(i: number) {
    const node = track.current;
    if (node) node.scrollTo({ left: i * node.clientWidth, behavior: "smooth" });
  }

  async function download(i: number) {
    const node = slideNodes.current[i];
    if (!node) return;
    const blob = await toBlob(node, { width: SLIDE_W, height: SLIDE_H, pixelRatio: 1, cacheBust: true });
    if (!blob) throw new Error("PNG oluşturulamadı");
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${fileStem}-${i + 1}-${slides[i].key}.png`;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  }

  async function run(label: string, work: () => Promise<void>) {
    setBusy(label);
    try {
      await work();
    } catch (error) {
      alert(`İndirme başarısız: ${error instanceof Error ? error.message : error}`);
    } finally {
      setBusy(null);
    }
  }

  async function copy() {
    await navigator.clipboard.writeText(caption ?? generated);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (!volumes.length) {
    return (
      <p className="rounded-xl border border-line bg-surface p-5 text-sm text-muted">
        Bu hafta için katalogda çıkış tarihi olan cilt yok. Başka bir haftaya bakabilirsin.
      </p>
    );
  }

  const button = "inline-flex min-h-11 items-center justify-center rounded-lg border border-line bg-surface px-3 text-sm font-semibold text-ink-2 hover:border-line-strong hover:text-accent disabled:opacity-50";

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,440px)_minmax(0,1fr)]">
      <section className="space-y-3" aria-label="Önizleme">
        <div className="overflow-hidden rounded-xl border border-line bg-surface">
          <div className="relative">
            <div
              ref={track}
              onScroll={(e) => setIndex(Math.round(e.currentTarget.scrollLeft / e.currentTarget.clientWidth))}
              className="flex snap-x snap-mandatory overflow-x-auto [scrollbar-width:none]"
            >
              {slides.map((s, i) => (
                <div key={s.key} className="w-full shrink-0 snap-center">
                  <ScaledSlide slideRef={(node) => { slideNodes.current[i] = node; }}>{s.node}</ScaledSlide>
                </div>
              ))}
            </div>
            {current > 0 ? (
              <button type="button" aria-label="Önceki sayfa" onClick={() => go(current - 1)}
                className="absolute top-1/2 left-2 grid size-11 -translate-y-1/2 place-items-center rounded-full bg-white/90 text-ink shadow">‹</button>
            ) : null}
            {current < slides.length - 1 ? (
              <button type="button" aria-label="Sonraki sayfa" onClick={() => go(current + 1)}
                className="absolute top-1/2 right-2 grid size-11 -translate-y-1/2 place-items-center rounded-full bg-white/90 text-ink shadow">›</button>
            ) : null}
          </div>
          <div className="flex justify-center gap-1 py-2">
            {slides.map((s, i) => (
              <button key={s.key} type="button" aria-label={`Sayfa ${i + 1}: ${s.label}`} onClick={() => go(i)}
                className="grid size-6 place-items-center">
                <span className={`size-2 rounded-full ${i === current ? "bg-new" : "bg-line-strong"}`} />
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className={button} disabled={busy !== null}
            onClick={() => run("bu", () => download(current))}>
            {busy === "bu" ? "Hazırlanıyor…" : "Bu sayfayı PNG indir"}
          </button>
          <button type="button" className={button} disabled={busy !== null}
            onClick={() => run("hepsi", async () => {
              for (let i = 0; i < slides.length; i++) {
                await download(i);
                await new Promise((r) => setTimeout(r, 400));
              }
            })}>
            {busy === "hepsi" ? "Hazırlanıyor…" : `Hepsini indir (${slides.length})`}
          </button>
        </div>
        <p className="text-xs text-muted">Görseller 1080×1350 (Instagram 4:5). Tarayıcı birden çok dosya için izin isteyebilir.</p>
      </section>

      <div className="space-y-8">
        <section className="space-y-3">
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="font-semibold text-ink">Açıklama metni</h2>
            <button type="button" className={button} onClick={copy}>{copied ? "Kopyalandı" : "Kopyala"}</button>
          </div>
          <label className="sr-only" htmlFor="ig-caption">Açıklama metni</label>
          <textarea id="ig-caption" value={caption ?? generated} onChange={(e) => setCaption(e.target.value)}
            rows={13} className="w-full rounded-lg border border-line-strong bg-surface p-3 text-sm text-ink" />
          {caption !== null ? (
            <button type="button" className="text-sm font-semibold text-new hover:underline" onClick={() => setCaption(null)}>
              Otomatik metne dön
            </button>
          ) : null}
        </section>

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
