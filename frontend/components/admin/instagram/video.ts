/**
 * Instagram Reels videos made in the browser: frames are drawn on a canvas
 * and encoded to an H.264 MP4 (WebCodecs through mediabunny, loaded only
 * when a video is made). No sound: music is added in Instagram, from its
 * own licensed library.
 */

import { toCanvas } from "html-to-image";
import { C, SLIDE_H, SLIDE_W } from "./slides";

export const VIDEO_W = 1080;
export const VIDEO_H = 1920;
export const FPS = 30;

export type Draw = (ctx: CanvasRenderingContext2D, t: number) => void;

/** Encodes `duration` seconds of `draw` to an MP4; `onProgress` gets 0..1. */
export async function encodeMp4(duration: number, draw: Draw, onProgress: (done: number) => void): Promise<Blob> {
  const { BufferTarget, CanvasSource, Mp4OutputFormat, Output, QUALITY_HIGH, getFirstEncodableVideoCodec } =
    await import("mediabunny");
  const codec = await getFirstEncodableVideoCodec(["avc", "hevc"], { width: VIDEO_W, height: VIDEO_H });
  if (!codec) {
    throw new Error("Bu tarayıcı MP4 video oluşturamıyor. Bilgisayarda Chrome ya da Edge'in, telefonda Safari'nin güncel sürümünü dene.");
  }
  const canvas = document.createElement("canvas");
  canvas.width = VIDEO_W;
  canvas.height = VIDEO_H;
  const ctx = canvas.getContext("2d")!;
  const output = new Output({ format: new Mp4OutputFormat({ fastStart: "in-memory" }), target: new BufferTarget() });
  const source = new CanvasSource(canvas, { codec, bitrate: QUALITY_HIGH, keyFrameInterval: 1 });
  output.addVideoTrack(source, { frameRate: FPS });
  await output.start();
  const frames = Math.round(duration * FPS);
  try {
    for (let i = 0; i < frames; i++) {
      ctx.save();
      draw(ctx, i / FPS);
      ctx.restore();
      await source.add(i / FPS, 1 / FPS);
      if (i % 15 === 0) onProgress(i / frames);
    }
    await output.finalize();
  } catch (error) {
    await output.cancel().catch(() => {});
    throw error;
  }
  onProgress(1);
  return new Blob([output.target.buffer!], { type: "video/mp4" });
}

export const clamp = (v: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));
export const easeInOut = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2);
export const easeOut = (x: number) => 1 - (1 - x) ** 3;
/** 0 before `from`, 1 after `from + length`, eased in between. */
export const phase = (t: number, from: number, length: number, ease = easeOut) => ease(clamp((t - from) / length));

/** The page's font families (next/font names them), for canvas text. */
export function fontFamilies(): { display: string; body: string } {
  const style = getComputedStyle(document.body);
  const read = (name: string, fallback: string) => {
    const family = style.getPropertyValue(name).trim();
    return family ? `${family}, ${fallback}` : fallback;
  };
  return { display: read("--font-display-face", "Georgia, serif"), body: read("--font-body", "system-ui, sans-serif") };
}

export async function loadFonts({ display, body }: { display: string; body: string }) {
  await Promise.all([`500 40px ${display}`, `700 120px ${display}`, `700 40px ${body}`].map((f) => document.fonts.load(f, "Bu hafta çıkanlar ĞŞİ")))
    .catch(() => {});
}

/** A cover image fetched as a bitmap (canvas-safe), or null when it fails. */
export async function loadImage(url: string): Promise<ImageBitmap | null> {
  try {
    const response = await fetch(url, { mode: "cors" });
    if (!response.ok) return null;
    return await createImageBitmap(await response.blob());
  } catch {
    return null;
  }
}

/** A slide node as drawn in the preview, captured at full size. */
export function captureSlide(node: HTMLElement): Promise<HTMLCanvasElement> {
  return toCanvas(node, { width: SLIDE_W, height: SLIDE_H, pixelRatio: 1, cacheBust: true });
}

export function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
}

/** `image` scaled to cover the video, blurred and darkened: a backdrop. */
function backdrop(image: HTMLCanvasElement): HTMLCanvasElement {
  const out = document.createElement("canvas");
  out.width = VIDEO_W;
  out.height = VIDEO_H;
  const o = out.getContext("2d")!;
  // Overscan, so the blur does not fade in from the edges.
  const scale = Math.max(VIDEO_W / image.width, VIDEO_H / image.height) * 1.15;
  const w = image.width * scale;
  const h = image.height * scale;
  if (typeof o.filter === "string") {
    o.filter = "blur(48px)";
    o.drawImage(image, (VIDEO_W - w) / 2, (VIDEO_H - h) / 2, w, h);
    o.filter = "none";
  } else {
    // No canvas filter (older Safari): shrink, then grow back in steps.
    let step: HTMLCanvasElement = image;
    for (const size of [64, 16, 64, 270]) {
      const next = document.createElement("canvas");
      next.width = size;
      next.height = Math.round((size * VIDEO_H) / VIDEO_W);
      const n = next.getContext("2d")!;
      n.imageSmoothingQuality = "high";
      const k = Math.max(next.width / step.width, next.height / step.height) * (step === image ? 1.15 : 1);
      n.drawImage(step, (next.width - step.width * k) / 2, (next.height - step.height * k) / 2, step.width * k, step.height * k);
      step = next;
    }
    o.imageSmoothingQuality = "high";
    o.drawImage(step, 0, 0, VIDEO_W, VIDEO_H);
  }
  o.fillStyle = "rgba(0,0,0,0.28)";
  o.fillRect(0, 0, VIDEO_W, VIDEO_H);
  return out;
}

export type ReelPace = { hold: number; move: number };

export const PACES: Record<string, { label: string; pace: ReelPace }> = {
  hizli: { label: "Hızlı", pace: { hold: 2.2, move: 0.5 } },
  normal: { label: "Normal", pace: { hold: 3.2, move: 0.6 } },
  yavas: { label: "Yavaş", pace: { hold: 4.5, move: 0.7 } },
};

/** Where the 4:5 slide sits in the 9:16 video: clear of Instagram's top bar
 * and of the caption over the bottom of a Reel. */
const CARD_W = 900;
const CARD_H = (CARD_W * SLIDE_H) / SLIDE_W;
const CARD_X = (VIDEO_W - CARD_W) / 2;
const CARD_Y = 300;

/** The carousel as a Reel: each slide held with a slow zoom, then pushed
 * aside by the next one, over a blurred copy of itself. */
export function slideReel(slides: HTMLCanvasElement[], { hold, move }: ReelPace): { duration: number; draw: Draw } {
  const grounds = slides.map(backdrop);
  const step = hold + move;
  const duration = slides.length * step - move + 0.4;

  function card(ctx: CanvasRenderingContext2D, i: number, dx: number, zoom: number) {
    const x = CARD_X + dx;
    ctx.save();
    ctx.shadowColor = "rgba(0,0,0,0.35)";
    ctx.shadowBlur = 60;
    ctx.shadowOffsetY = 24;
    roundRect(ctx, x, CARD_Y, CARD_W, CARD_H, 28);
    ctx.fillStyle = C.paper;
    ctx.fill();
    ctx.restore();
    ctx.save();
    roundRect(ctx, x, CARD_Y, CARD_W, CARD_H, 28);
    ctx.clip();
    const w = CARD_W * zoom;
    const h = CARD_H * zoom;
    ctx.drawImage(slides[i], x - (w - CARD_W) / 2, CARD_Y - (h - CARD_H) / 2, w, h);
    ctx.restore();
  }

  const draw: Draw = (ctx, t) => {
    const i = Math.min(Math.floor(t / step), slides.length - 1);
    const local = t - i * step;
    const moving = i < slides.length - 1 && local > hold ? easeInOut(clamp((local - hold) / move)) : 0;
    const zoom = (k: number, at: number) => 1 + 0.035 * clamp(at / (k === slides.length - 1 ? hold + 0.4 : step));
    ctx.drawImage(grounds[i], 0, 0);
    if (moving) {
      ctx.globalAlpha = moving;
      ctx.drawImage(grounds[i + 1], 0, 0);
      ctx.globalAlpha = 1;
      const shift = moving * (VIDEO_W + 40);
      card(ctx, i, -shift, zoom(i, local));
      card(ctx, i + 1, VIDEO_W + 40 - shift, 1);
    } else {
      card(ctx, i, 0, zoom(i, local));
    }
  };
  return { duration, draw };
}
