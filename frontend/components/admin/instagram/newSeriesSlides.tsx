/**
 * The "Yeni seri" post's main slide: the first volume's cover on a sunburst,
 * a "yeni seri" stamp, the title, a short blurb and a few facts. Same size,
 * colors and inline-style rule as the weekly slides (see slides.tsx). No
 * prices or store names, and no Japan/Turkey series status.
 */

import type { NewSeries } from "@/services/instagram";
import type { Palette } from "./coverColors";
import type { TextField } from "./parts";
import { Brand, C, CoverArt, DISPLAY, Frame, Lines, dayLabel } from "./slides";

/** Fixed background and stamp colors; the panel adds ones from the cover. */
export const PALETTES: { key: string; label: string; palette: Palette }[] = [
  { key: "indigo", label: "Lacivert", palette: { ground: C.indigo, accent: C.accent } },
  { key: "ink", label: "Siyah", palette: { ground: C.ink, accent: C.accent } },
  { key: "green", label: "Yeşil", palette: { ground: "#4f6b5a", accent: C.accent } },
];

const BLURB_MAX = 190;

/** The blurb cut to whole sentences that fit; a long first sentence is cut at a word. */
export function shortBlurb(text: string | null): string {
  if (!text) return "";
  const flat = text.replace(/\s+/g, " ").trim();
  if (flat.length <= BLURB_MAX) return flat;
  let out = "";
  for (const sentence of flat.match(/[^.!?…]+[.!?…]+["'”’)]*\s*/g) ?? []) {
    if ((out + sentence).trim().length > BLURB_MAX) break;
    out += sentence;
  }
  if (out.trim()) return out.trim();
  return `${flat.slice(0, BLURB_MAX).replace(/\s+\S*$/, "")}…`;
}

export type NewSeriesText = "rozetUst" | "rozetAlt" | "baslik" | "metin" | "etiketler" | "link";

export const newSeriesTexts = (s: NewSeries): TextField<NewSeriesText>[] => [
  { id: "rozetUst", label: "Rozet üst satır", value: "YENİ SERİ" },
  { id: "rozetAlt", label: "Rozet alt satır", value: s.upcoming ? "geliyor" : "başladı" },
  { id: "baslik", label: "Seri adı", value: s.title, multiline: true },
  { id: "metin", label: "Kısa tanıtım", value: shortBlurb(s.description), multiline: true },
  {
    id: "etiketler", label: "Etiketler (her satır bir etiket)", multiline: true,
    value: [s.publisher, `${s.first_number || 1}. cilt · ${dayLabel(s.release_date)}`, s.author].filter(Boolean).join("\n"),
  },
  { id: "link", label: "Link", value: "yomiba.net" },
];

export function NewSeriesSlide({ s, tx, palette: { ground, accent }, page }: {
  s: NewSeries; tx: Record<NewSeriesText, string>; palette: Palette; page: string;
}) {
  const longest = Math.max(...tx.baslik.split("\n").map((line) => line.length));
  const titleSize = longest > 22 ? 76 : longest > 14 ? 100 : 132;
  const chips = tx.etiketler.split("\n").map((c) => c.trim()).filter(Boolean);
  const cover = { cover_url: s.cover_url, series_title: s.title, number: s.first_number, covers_from: null, covers_to: null };
  return (
    <Frame background={ground} color={C.surface}>
      <div aria-hidden style={{ position: "absolute", left: 540, top: 470, width: 3000, height: 3000, marginLeft: -1500, marginTop: -1500, background: "repeating-conic-gradient(from 0deg, rgba(255,253,248,0.13) 0deg 1deg, transparent 1deg 5deg)" }} />
      <div aria-hidden style={{ position: "absolute", left: 540, top: 470, width: 700, height: 700, marginLeft: -350, marginTop: -350, borderRadius: "50%", background: ground }} />
      <div aria-hidden style={{ position: "absolute", right: 64, top: 170, display: "flex", flexDirection: "column", gap: 8, fontFamily: DISPLAY, fontSize: 72, fontWeight: 900, lineHeight: 1, color: "rgba(255,253,248,0.2)" }}>
        {[..."新連載"].map((ch) => <span key={ch}>{ch}</span>)}
      </div>
      <div style={{ position: "absolute", left: 72, right: 72, top: 64 }}><Brand page={page} dark /></div>
      <CoverArt v={cover} border style={{
        position: "absolute", left: 350, top: 190, width: 380, height: 570, borderRadius: 12,
        transform: "rotate(-3deg)", boxShadow: "0 30px 70px rgba(0,0,0,0.5)",
      }} />
      {tx.rozetUst || tx.rozetAlt ? (
        <div style={{ position: "absolute", left: 150, top: 230, width: 230, height: 230, borderRadius: "50%", background: accent, color: C.surface, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", textAlign: "center", transform: "rotate(-12deg)", boxShadow: `0 0 0 8px ${ground}, 0 0 0 12px ${accent}` }}>
          <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: 2 }}>{tx.rozetUst}</div>
          <div style={{ fontFamily: DISPLAY, fontSize: 50, fontWeight: 900, lineHeight: 1 }}>{tx.rozetAlt}</div>
        </div>
      ) : null}
      <div style={{ position: "absolute", left: 72, right: 72, bottom: 64, display: "flex", flexDirection: "column", gap: 22 }}>
        <h1 style={{ margin: 0, fontFamily: DISPLAY, fontSize: titleSize, lineHeight: 0.92, fontWeight: 900, letterSpacing: -3 }}>
          <Lines text={tx.baslik} />
        </h1>
        {tx.metin ? (
          <div style={{ fontSize: 30, lineHeight: 1.35, color: "rgba(255,253,248,0.88)", maxWidth: 900 }}><Lines text={tx.metin} /></div>
        ) : null}
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 14 }}>
          {chips.map((chip, i) => (
            <div key={i} style={{ border: "2px solid rgba(255,253,248,0.6)", borderRadius: 999, padding: "10px 20px", fontSize: 24, fontWeight: 700 }}>{chip}</div>
          ))}
          {tx.link ? (
            <div style={{ marginLeft: "auto", background: C.surface, color: C.ink, borderRadius: 999, padding: "10px 20px", fontSize: 24, fontWeight: 800 }}>{tx.link}</div>
          ) : null}
        </div>
      </div>
    </Frame>
  );
}
