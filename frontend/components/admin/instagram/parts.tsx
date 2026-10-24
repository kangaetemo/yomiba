"use client";

/**
 * The pieces every Instagram draft shares: the swipeable preview with PNG
 * download, and the editable caption with a copy button.
 */

import { toBlob } from "html-to-image";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { SLIDE_H, SLIDE_W } from "./slides";

export type Slide = { key: string; label: string; node: ReactNode };

export const BUTTON = "inline-flex min-h-11 items-center justify-center rounded-lg border border-line bg-surface px-3 text-sm font-semibold text-ink-2 hover:border-line-strong hover:text-accent disabled:opacity-50";

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

export function SlideCarousel({ slides, fileStem }: { slides: Slide[]; fileStem: string }) {
  const [index, setIndex] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const track = useRef<HTMLDivElement>(null);
  const slideNodes = useRef<(HTMLDivElement | null)[]>([]);
  const current = Math.min(index, slides.length - 1);

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

  return (
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
        <button type="button" className={BUTTON} disabled={busy !== null}
          onClick={() => run("bu", () => download(current))}>
          {busy === "bu" ? "Hazırlanıyor…" : "Bu sayfayı PNG indir"}
        </button>
        <button type="button" className={BUTTON} disabled={busy !== null}
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
  );
}

/** The generated caption, editable; "Otomatik metne dön" drops the edits. */
export function CaptionEditor({ generated, caption, setCaption, rows = 13 }: {
  generated: string; caption: string | null; setCaption: (value: string | null) => void; rows?: number;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(caption ?? generated);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-semibold text-ink">Açıklama metni</h2>
        <button type="button" className={BUTTON} onClick={copy}>{copied ? "Kopyalandı" : "Kopyala"}</button>
      </div>
      <label className="sr-only" htmlFor="ig-caption">Açıklama metni</label>
      <textarea id="ig-caption" value={caption ?? generated} onChange={(e) => setCaption(e.target.value)}
        rows={rows} className="w-full rounded-lg border border-line-strong bg-surface p-3 text-sm text-ink" />
      {caption !== null ? (
        <button type="button" className="text-sm font-semibold text-new hover:underline" onClick={() => setCaption(null)}>
          Otomatik metne dön
        </button>
      ) : null}
    </section>
  );
}
