"use client";

/**
 * Reels videos of a draft: the carousel's slides one after another, or a
 * promo of covers drifting past. Made in the browser on request, previewed
 * here and downloaded as MP4; nothing is uploaded anywhere.
 */

import { useEffect, useRef, useState } from "react";
import { BUTTON, type TextField } from "./parts";
import { coverPromo, type PromoText, type PromoTexts } from "./promo";
import {
  PACES, captureSlide, encodeMp4, fontFamilies, loadFonts, loadImage, slideReel, type Draw,
} from "./video";

type Made = { url: string; name: string; seconds: number };

/** One video at a time: its progress, the result, the error. */
function useVideoJob() {
  const [progress, setProgress] = useState<number | null>(null);
  const [made, setMade] = useState<Made | null>(null);
  const [error, setError] = useState<string | null>(null);
  const url = useRef<string | null>(null);
  useEffect(() => () => { if (url.current) URL.revokeObjectURL(url.current); }, []);

  async function run(name: string, prepare: () => Promise<{ duration: number; draw: Draw }>) {
    setError(null);
    setProgress(0);
    try {
      const { duration, draw } = await prepare();
      const blob = await encodeMp4(duration, draw, setProgress);
      if (url.current) URL.revokeObjectURL(url.current);
      url.current = URL.createObjectURL(blob);
      setMade({ url: url.current, name, seconds: Math.round(duration) });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setProgress(null);
    }
  }
  return { progress, made, error, run, busy: progress !== null };
}

function VideoResult({ job }: { job: ReturnType<typeof useVideoJob> }) {
  const { progress, made, error } = job;
  return (
    <>
      {progress !== null ? (
        <div className="space-y-1" role="status">
          <div className="h-2 overflow-hidden rounded-full bg-surface-2">
            <div className="h-full bg-new transition-[width]" style={{ width: `${Math.round(progress * 100)}%` }} />
          </div>
          <p className="text-xs text-muted">Video hazırlanıyor, %{Math.round(progress * 100)}. Sekmeyi kapatma.</p>
        </div>
      ) : null}
      {error ? <p className="text-sm text-red-700">Video oluşturulamadı: {error}</p> : null}
      {made && progress === null ? (
        <div className="flex flex-wrap items-end gap-4">
          <video src={made.url} controls loop playsInline muted className="aspect-[9/16] w-40 rounded-lg border border-line bg-black" />
          <div className="space-y-2">
            <a href={made.url} download={made.name} className={BUTTON}>MP4 indir</a>
            <p className="text-xs text-muted">{made.seconds} saniye, 1080×1920, sessiz.</p>
          </div>
        </div>
      ) : null}
    </>
  );
}

/** "Reels videosu": the carousel's slides as one 9:16 video. */
export function SlideReel({ slideNodes, count, fileStem }: {
  slideNodes: () => (HTMLDivElement | null)[]; count: number; fileStem: string;
}) {
  const job = useVideoJob();
  const [pace, setPace] = useState("normal");
  const total = Math.round(count * (PACES[pace].pace.hold + PACES[pace].pace.move));

  function make() {
    job.run(`${fileStem}-reels.mp4`, async () => {
      const nodes = slideNodes().slice(0, count);
      if (nodes.some((n) => !n)) throw new Error("Önizleme henüz hazır değil");
      const frames = [];
      for (const node of nodes) frames.push(await captureSlide(node!));
      return slideReel(frames, PACES[pace].pace);
    });
  }

  return (
    <section className="space-y-3 rounded-xl border border-line bg-surface p-4">
      <h2 className="font-semibold text-ink">Reels videosu</h2>
      <p className="text-sm text-muted">
        Bu sayfalar sırayla, kayarak geçen dikey bir video olur. Yazı değişikliklerin videoya da girer.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-sm font-semibold text-ink-2" htmlFor={`ig-pace-${fileStem}`}>Hız</label>
        <select id={`ig-pace-${fileStem}`} value={pace} onChange={(e) => setPace(e.target.value)} disabled={job.busy}
          className="min-h-11 rounded-lg border border-line-strong bg-surface px-2 text-sm text-ink">
          {Object.entries(PACES).map(([key, p]) => <option key={key} value={key}>{p.label}</option>)}
        </select>
        <button type="button" className={BUTTON} disabled={job.busy} onClick={make}>
          {job.busy ? "Hazırlanıyor…" : `Video yap (~${total} sn)`}
        </button>
      </div>
      <VideoResult job={job} />
      <p className="text-xs text-muted">Müziği Instagram&apos;da eklersin: Reels yüklerken &quot;Ses ekle&quot; kısmından.</p>
    </section>
  );
}

/** "Tanıtım videosu": covers drifting past, a headline, the end card. */
export function CoverPromo({ covers, fields, fileStem }: {
  covers: (string | null)[]; fields: TextField<PromoText>[]; fileStem: string;
}) {
  const job = useVideoJob();
  const [edits, setEdits] = useState<Partial<PromoTexts>>({});
  const tx = Object.fromEntries(fields.map((f) => [f.id, edits[f.id] ?? f.value])) as PromoTexts;
  const urls = [...new Set(covers.filter((c): c is string => !!c))];

  function make() {
    job.run(`${fileStem}-tanitim.mp4`, async () => {
      const fonts = fontFamilies();
      const [images] = await Promise.all([Promise.all(urls.map(loadImage)), loadFonts(fonts)]);
      return coverPromo(images.filter((i): i is ImageBitmap => !!i), tx, fonts);
    });
  }

  const input = "w-full rounded-lg border border-line-strong bg-surface p-2 text-sm text-ink";
  return (
    <section className="space-y-3 rounded-xl border border-line bg-surface p-4">
      <h2 className="font-semibold text-ink">Tanıtım videosu</h2>
      <p className="text-sm text-muted">
        {urls.length} kapak eğik sıralar halinde kayarak geçer, üstünde başlık çıkar, sonunda yomiba kapanışı gelir. 11 saniyelik dikey Reels videosu.
      </p>
      {fields.map((f) => {
        const id = `ig-promo-${fileStem}-${f.id}`;
        const value = tx[f.id];
        return (
          <div key={f.id} className="space-y-1">
            <div className="flex items-baseline justify-between gap-3">
              <label htmlFor={id} className="text-sm font-semibold text-ink-2">{f.label}</label>
              {f.id in edits ? (
                <button type="button" className="text-xs font-semibold text-new hover:underline"
                  onClick={() => setEdits((all) => {
                    const kept = { ...all };
                    delete kept[f.id];
                    return kept;
                  })}>Geri al</button>
              ) : null}
            </div>
            {f.multiline ? (
              <textarea id={id} value={value} rows={Math.max(value.split("\n").length, 2)} className={input}
                onChange={(e) => setEdits((all) => ({ ...all, [f.id]: e.target.value }))} />
            ) : (
              <input id={id} value={value} className={`${input} min-h-11`}
                onChange={(e) => setEdits((all) => ({ ...all, [f.id]: e.target.value }))} />
            )}
          </div>
        );
      })}
      <button type="button" className={BUTTON} disabled={job.busy || !urls.length} onClick={make}>
        {job.busy ? "Hazırlanıyor…" : "Tanıtım videosu yap"}
      </button>
      <VideoResult job={job} />
    </section>
  );
}
