/**
 * Background colors picked from a cover, for the "Yeni seri" post. The
 * cover's strongest hue becomes a dark ground (white text stays readable on
 * it) and the stamp takes the cover's second hue, or the complementary one
 * when the cover has a single color.
 */

export type Palette = { ground: string; accent: string };

type Hsl = { h: number; s: number; l: number };

const BINS = 24;
/** Contrast of the slide's off-white text on each color, at least. */
const GROUND_CONTRAST = 7;
const ACCENT_CONTRAST = 4.5;

function toHsl(r: number, g: number, b: number): Hsl {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  const d = max - min;
  if (!d) return { h: 0, s: 0, l };
  const s = d / (1 - Math.abs(2 * l - 1));
  const h = max === r ? ((g - b) / d + 6) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return { h: h * 60, s, l };
}

function toRgb({ h, s, l }: Hsl): [number, number, number] {
  const k = (n: number) => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return [f(0), f(8), f(4)].map((v) => Math.round(v * 255)) as [number, number, number];
}

const hex = (c: Hsl) => `#${toRgb(c).map((v) => v.toString(16).padStart(2, "0")).join("")}`;

function luminance([r, g, b]: [number, number, number]): number {
  const lin = (v: number) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

/** Contrast of the slides' text color (#fffdf8) on `c`. */
const contrast = (c: Hsl) => (luminance([255, 253, 248]) + 0.05) / (luminance(toRgb(c)) + 0.05);

/** `c` darkened until white text on it reaches `min` contrast. */
function readable(c: Hsl, min: number): Hsl {
  let out = c;
  while (contrast(out) < min && out.l > 0.05) out = { ...out, l: out.l - 0.01 };
  return out;
}

const hueGap = (a: number, b: number) => Math.min(Math.abs(a - b), 360 - Math.abs(a - b));

/** The two strongest hues of an image (saturation-weighted), strongest first. */
function hues(pixels: Uint8ClampedArray): { h: number; s: number }[] {
  const weight = new Array<number>(BINS).fill(0);
  const sx = new Array<number>(BINS).fill(0);
  const sy = new Array<number>(BINS).fill(0);
  const sat = new Array<number>(BINS).fill(0);
  for (let i = 0; i < pixels.length; i += 4) {
    if (pixels[i + 3] < 128) continue;
    const c = toHsl(pixels[i], pixels[i + 1], pixels[i + 2]);
    // Greys, near-black and near-white carry no hue worth matching.
    if (c.s < 0.2 || c.l < 0.1 || c.l > 0.92) continue;
    const bin = Math.floor(c.h / (360 / BINS)) % BINS;
    const w = c.s * (1 - Math.abs(2 * c.l - 1));
    weight[bin] += w;
    sx[bin] += Math.cos((c.h * Math.PI) / 180) * w;
    sy[bin] += Math.sin((c.h * Math.PI) / 180) * w;
    sat[bin] += c.s * w;
  }
  // A hue spreads over neighbouring bins: score each bin with both neighbours.
  const score = (b: number) => weight[(b + BINS - 1) % BINS] + weight[b] + weight[(b + 1) % BINS];
  const total = weight.reduce((a, b) => a + b, 0);
  const picked: { h: number; s: number }[] = [];
  for (const b of [...weight.keys()].sort((x, y) => score(y) - score(x))) {
    if (!weight[b] || score(b) < total * 0.08) break;
    const h = ((Math.atan2(sy[b], sx[b]) * 180) / Math.PI + 360) % 360;
    if (picked.some((p) => hueGap(p.h, h) < 40)) continue;
    picked.push({ h, s: sat[b] / weight[b] });
    if (picked.length === 2) break;
  }
  return picked;
}

/** Palettes from the cover: matching, and with ground and stamp swapped
 * (null when the image can't be read or has no color to speak of). */
export async function coverPalettes(url: string): Promise<{ match: Palette; contrast: Palette } | null> {
  const img = new Image();
  img.crossOrigin = "anonymous";
  img.src = url;
  try {
    await img.decode();
  } catch {
    return null;
  }
  const canvas = document.createElement("canvas");
  canvas.width = 48;
  canvas.height = 72;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  let pixels: Uint8ClampedArray;
  try {
    pixels = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
  } catch {
    return null; // a cross-origin image without CORS taints the canvas
  }
  const [first, second] = hues(pixels);
  if (!first) return null;
  const other = second ?? { h: (first.h + 180) % 360, s: first.s };
  const ground = (c: { h: number; s: number }) =>
    hex(readable({ h: c.h, s: Math.min(Math.max(c.s, 0.45), 0.7), l: 0.3 }, GROUND_CONTRAST));
  const accent = (c: { h: number; s: number }) =>
    hex(readable({ h: c.h, s: Math.min(Math.max(c.s, 0.6), 0.85), l: 0.5 }, ACCENT_CONTRAST));
  return {
    match: { ground: ground(first), accent: accent(other) },
    contrast: { ground: ground(other), accent: accent(first) },
  };
}
