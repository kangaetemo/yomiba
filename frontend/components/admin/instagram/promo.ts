/**
 * The cover promo Reel: rows of real covers drifting past at a tilt, a
 * headline over them, then the yomiba end card. Drawn on a canvas frame by
 * frame (see video.ts), in the slides' colors.
 */

import type { TextField } from "./parts";
import { C } from "./slides";
import { VIDEO_H, VIDEO_W, clamp, phase, roundRect, type Draw } from "./video";

export type PromoText = "etiket" | "baslik" | "son" | "link";

export type PromoTexts = Record<PromoText, string>;

export const promoTexts = (etiket: string, baslik: string, son: string, link: string): TextField<PromoText>[] => [
  { id: "etiket", label: "Üst etiket", value: etiket },
  { id: "baslik", label: "Başlık (son satır renkli)", value: baslik, multiline: true },
  { id: "son", label: "Kapanış yazısı", value: son, multiline: true },
  { id: "link", label: "Link", value: link },
];

const COVER_W = 280;
const COVER_H = 420;
const PITCH = COVER_W + 34;
const ROW_PITCH = COVER_H + 44;
const ROWS = [-2, -1, 0, 1, 2];
const TILT = (-11 * Math.PI) / 180;
const SPEED = 70;
/** Seconds: headline in, headline out, end card in. */
const TEXT_IN = 0.9;
const TEXT_OUT = 7.2;
const END_IN = 7.7;
export const PROMO_DURATION = 11.5;

type Fonts = { display: string; body: string };

/** Lines of `text` in `font`, shrunk so the widest fits `maxWidth`. */
function fit(ctx: CanvasRenderingContext2D, lines: string[], weight: number, size: number, family: string, maxWidth: number) {
  ctx.font = `${weight} ${size}px ${family}`;
  const widest = Math.max(...lines.map((l) => ctx.measureText(l).width), 1);
  const scaled = Math.floor(size * Math.min(1, maxWidth / widest));
  ctx.font = `${weight} ${scaled}px ${family}`;
  return scaled;
}

/** A tilted label block, like the slides' "etiket". */
function label(ctx: CanvasRenderingContext2D, text: string, y: number, fonts: Fonts) {
  ctx.save();
  ctx.font = `800 34px ${fonts.body}`;
  ctx.letterSpacing = "4px";
  const w = ctx.measureText(text).width + 48;
  ctx.translate(VIDEO_W / 2, y);
  ctx.rotate((-1.5 * Math.PI) / 180);
  ctx.fillStyle = C.accent;
  ctx.fillRect(-w / 2, -34, w, 68);
  ctx.fillStyle = C.surface;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, 0, 2);
  ctx.restore();
}

export function coverPromo(covers: ImageBitmap[], tx: PromoTexts, fonts: Fonts): { duration: number; draw: Draw } {
  const n = covers.length;

  function cover(ctx: CanvasRenderingContext2D, image: ImageBitmap | undefined, x: number, y: number) {
    ctx.save();
    roundRect(ctx, x, y, COVER_W, COVER_H, 14);
    ctx.clip();
    if (image) {
      const scale = Math.max(COVER_W / image.width, COVER_H / image.height);
      ctx.drawImage(image, x + (COVER_W - image.width * scale) / 2, y + (COVER_H - image.height * scale) / 2,
        image.width * scale, image.height * scale);
    } else {
      ctx.fillStyle = C.ink2;
      ctx.fillRect(x, y, COVER_W, COVER_H);
      ctx.fillStyle = C.faint;
      ctx.font = `120px ${fonts.display}`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("読", x + COVER_W / 2, y + COVER_H / 2);
    }
    ctx.restore();
  }

  function wall(ctx: CanvasRenderingContext2D, t: number) {
    const arrive = phase(t, 0, 1.4);
    ctx.save();
    ctx.globalAlpha = phase(t, 0, 0.6);
    ctx.translate(VIDEO_W / 2, VIDEO_H / 2);
    ctx.rotate(TILT);
    const reach = 1400;
    for (const r of ROWS) {
      const dir = r % 2 ? 1 : -1;
      const offset = dir * (SPEED * t + (1 - arrive) * -900) + r * 97;
      const y = r * ROW_PITCH - COVER_H / 2;
      const first = Math.floor((-reach - offset) / PITCH);
      const last = Math.ceil((reach - offset) / PITCH);
      for (let k = first; k <= last; k++) {
        const pick = n ? covers[(((k + r * 3) % n) + n) % n] : undefined;
        cover(ctx, pick, k * PITCH + offset - COVER_W / 2, y);
      }
    }
    ctx.restore();
  }

  function headline(ctx: CanvasRenderingContext2D, t: number) {
    const shown = phase(t, TEXT_IN, 0.6) * (1 - phase(t, TEXT_OUT, 0.45));
    if (!shown) return;
    // A dark band behind the text so it reads over any cover.
    const band = ctx.createLinearGradient(0, VIDEO_H / 2 - 620, 0, VIDEO_H / 2 + 620);
    band.addColorStop(0, "rgba(31,27,22,0)");
    band.addColorStop(0.3, "rgba(31,27,22,0.86)");
    band.addColorStop(0.7, "rgba(31,27,22,0.86)");
    band.addColorStop(1, "rgba(31,27,22,0)");
    ctx.globalAlpha = shown;
    ctx.fillStyle = band;
    ctx.fillRect(0, 0, VIDEO_W, VIDEO_H);

    const lines = tx.baslik.split("\n").filter((l) => l.trim());
    ctx.save();
    const size = fit(ctx, lines, 900, 140, fonts.display, 940);
    const lineH = size * 1.02;
    const top = VIDEO_H / 2 - ((lines.length - 1) * lineH) / 2 + 40;
    if (tx.etiket) {
      ctx.globalAlpha = phase(t, TEXT_IN, 0.5) * (1 - phase(t, TEXT_OUT, 0.45));
      label(ctx, tx.etiket, top - size * 0.5 - 90, fonts);
    }
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.letterSpacing = "-3px";
    lines.forEach((line, i) => {
      const enter = phase(t, TEXT_IN + 0.2 + i * 0.16, 0.55);
      ctx.globalAlpha = enter * (1 - phase(t, TEXT_OUT, 0.45));
      ctx.fillStyle = i === lines.length - 1 && lines.length > 1 ? C.accentSoft : C.paper;
      ctx.fillText(line, VIDEO_W / 2, top + i * lineH + (1 - enter) * 50);
    });
    ctx.restore();
    ctx.globalAlpha = 1;
  }

  function endCard(ctx: CanvasRenderingContext2D, t: number) {
    const shown = phase(t, END_IN, 0.6);
    if (!shown) return;
    ctx.globalAlpha = shown * 0.93;
    ctx.fillStyle = C.ink;
    ctx.fillRect(0, 0, VIDEO_W, VIDEO_H);
    ctx.save();
    const pop = phase(t, END_IN + 0.15, 0.6);
    ctx.globalAlpha = pop;
    ctx.translate(VIDEO_W / 2, VIDEO_H / 2 - 140);
    ctx.scale(0.92 + 0.08 * pop, 0.92 + 0.08 * pop);
    // The seal, as in the slides' brand mark.
    ctx.save();
    ctx.translate(0, -230);
    ctx.rotate((-3 * Math.PI) / 180);
    roundRect(ctx, -90, -90, 180, 180, 28);
    ctx.fillStyle = C.accent;
    ctx.fill();
    ctx.fillStyle = C.surface;
    ctx.font = `700 100px ${fonts.display}`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("読", 0, 6);
    ctx.restore();
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = C.paper;
    ctx.font = `500 120px ${fonts.display}`;
    ctx.fillText("yomiba", 0, -10);
    const lines = tx.son.split("\n").filter((l) => l.trim());
    const size = lines.length ? fit(ctx, lines, 600, 48, fonts.body, 900) : 48;
    ctx.fillStyle = C.surface3;
    lines.forEach((line, i) => ctx.fillText(line, 0, 130 + i * size * 1.3));
    if (tx.link) {
      const y = 130 + lines.length * size * 1.3 + 70;
      ctx.font = `800 52px ${fonts.body}`;
      const w = ctx.measureText(tx.link).width + 80;
      roundRect(ctx, -w / 2, y - 50, w, 100, 50);
      ctx.fillStyle = C.paper;
      ctx.fill();
      ctx.fillStyle = C.ink;
      ctx.fillText(tx.link, 0, y + 3);
    }
    ctx.restore();
    ctx.globalAlpha = 1;
  }

  const draw: Draw = (ctx, t) => {
    ctx.fillStyle = C.ink;
    ctx.fillRect(0, 0, VIDEO_W, VIDEO_H);
    wall(ctx, t);
    headline(ctx, t);
    endCard(ctx, t);
    // A soft fade at the very end, so a looping Reel does not jump.
    const out = clamp((t - (PROMO_DURATION - 0.35)) / 0.35);
    if (out) {
      ctx.globalAlpha = out;
      ctx.fillStyle = C.ink;
      ctx.fillRect(0, 0, VIDEO_W, VIDEO_H);
      ctx.globalAlpha = 1;
    }
  };
  return { duration: PROMO_DURATION, draw };
}
