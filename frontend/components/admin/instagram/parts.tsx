"use client";

/**
 * The pieces every Instagram draft shares: the swipeable preview with PNG
 * download, the slide texts the admin can rewrite by hand, and the editable
 * caption with a copy button.
 */

import { toBlob } from "html-to-image";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { SLIDE_H, SLIDE_W } from "./slides";

/** A text on a slide the admin may rewrite; `value` is the generated one.
 * In a multiline field each line of the text is a line on the slide. */
export type TextField<K extends string = string> = { id: K; label: string; value: string; multiline?: boolean };

export type Slide = { key: string; label: string; node: ReactNode; fields?: TextField[] };

/** Hand edits to slide texts, by slide key, then field id. */
export type TextEdits = ReturnType<typeof useTextEdits>;

export function useTextEdits() {
  const [edits, setEdits] = useState<Record<string, Record<string, string>>>({});
  /** Each field's text: the admin's edit, else the generated one. */
  function apply<K extends string>(slide: string, fields: TextField<K>[]): Record<K, string> {
    const own = edits[slide] ?? {};
    return Object.fromEntries(fields.map((f) => [f.id, own[f.id] ?? f.value])) as Record<K, string>;
  }
  return {
    edits,
    /** A slide drawn with its texts as edited; the editor lists `fields`. */
    slide<K extends string>(key: string, label: string, fields: TextField<K>[],
      draw: (tx: Record<K, string>) => ReactNode): Slide {
      return { key, label, fields, node: draw(apply(key, fields)) };
    },
    set(slide: string, id: string, value: string) {
      setEdits((all) => ({ ...all, [slide]: { ...all[slide], [id]: value } }));
    },
    /** Back to the generated text: one field, or the whole slide. */
    reset(slide: string, id?: string) {
      setEdits((all) => {
        const { [slide]: own, ...rest } = all;
        if (!id || !own) return rest;
        const kept = { ...own };
        delete kept[id];
        return Object.keys(kept).length ? { ...rest, [slide]: kept } : rest;
      });
    },
  };
}

/** The current slide's texts, editable; the preview and PNG follow. */
function SlideTextEditor({ slide, texts }: { slide: Slide; texts: TextEdits }) {
  const fields = slide.fields ?? [];
  const own = texts.edits[slide.key] ?? {};
  if (!fields.length) return null;
  return (
    <section className="space-y-3 rounded-xl border border-line bg-surface p-4">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-semibold text-ink">Bu sayfanın yazıları <span className="font-normal text-muted">({slide.label})</span></h2>
        {Object.keys(own).length ? (
          <button type="button" className="text-sm font-semibold text-new hover:underline" onClick={() => texts.reset(slide.key)}>
            Hepsini geri al
          </button>
        ) : null}
      </div>
      {fields.map((f) => {
        const id = `ig-text-${slide.key}-${f.id}`;
        const value = own[f.id] ?? f.value;
        const input = "w-full rounded-lg border border-line-strong bg-surface p-2 text-sm text-ink";
        return (
          <div key={f.id} className="space-y-1">
            <div className="flex items-baseline justify-between gap-3">
              <label htmlFor={id} className="text-sm font-semibold text-ink-2">{f.label}</label>
              {f.id in own ? (
                <button type="button" className="text-xs font-semibold text-new hover:underline" onClick={() => texts.reset(slide.key, f.id)}>
                  Geri al
                </button>
              ) : null}
            </div>
            {f.multiline ? (
              <textarea id={id} value={value} rows={Math.min(Math.max(value.split("\n").length, Math.ceil(value.length / 45), 2), 8)}
                onChange={(e) => texts.set(slide.key, f.id, e.target.value)} className={input} />
            ) : (
              <input id={id} value={value} onChange={(e) => texts.set(slide.key, f.id, e.target.value)} className={`${input} min-h-11`} />
            )}
          </div>
        );
      })}
      <p className="text-xs text-muted">Çok satırlı kutularda her satır görselde ayrı bir satır olur.</p>
    </section>
  );
}

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

export function SlideCarousel({ slides, fileStem, texts }: { slides: Slide[]; fileStem: string; texts: TextEdits }) {
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
      <SlideTextEditor slide={slides[current]} texts={texts} />
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
