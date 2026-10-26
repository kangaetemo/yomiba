/**
 * Instagram carousel slides, drawn at the post's real size (1080×1350, 4:5)
 * with inline styles only, so the PNG export (html-to-image) is exactly what
 * the preview shows. Colors are the site's light theme, fixed: a post does
 * not follow the viewer's theme.
 */

import { Fragment, type CSSProperties, type ReactNode } from "react";
import type { InstagramVolume, LaunchVolume } from "@/services/instagram";
import type { TextField } from "./parts";

export const SLIDE_W = 1080;
export const SLIDE_H = 1350;

export const C = {
  paper: "#f7f2e7",
  surface: "#fffdf8",
  surface3: "#e7dcc6",
  line: "#e4d9c3",
  ink: "#1f1b16",
  ink2: "#3d372e",
  muted: "#6a6153",
  faint: "#8a806d",
  accent: "#b8321b",
  accentSoft: "#f2b8a6",
  indigo: "#2f4f7a",
};
export const DISPLAY = "var(--font-display-face), Georgia, serif";
const BODY = "var(--font-body), system-ui, sans-serif";

const DAY = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "long", timeZone: "UTC" });
const WEEKDAY = new Intl.DateTimeFormat("tr-TR", { weekday: "long", timeZone: "UTC" });
const isoDate = (iso: string) => new Date(`${iso}T00:00:00Z`);

export const formatPrice = (value: number) =>
  `${value.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ₺`;
export const dayLabel = (iso: string) => DAY.format(isoDate(iso));
const weekdayLabel = (iso: string) => {
  const day = WEEKDAY.format(isoDate(iso));
  return `${day.charAt(0).toLocaleUpperCase("tr-TR")}${day.slice(1)} · ${dayLabel(iso)}`;
};

/** What a cover or a book title needs of a volume. */
type Book = Pick<LaunchVolume, "series_title" | "number" | "covers_from" | "covers_to" | "cover_url">;

/** "One Piece 105", "Dragon Ball 5 (9–10)". */
export function bookTitle(v: Omit<Book, "cover_url">): string {
  const span = v.covers_from && v.covers_to ? ` (${v.covers_from}–${v.covers_to})` : "";
  return `${v.series_title} ${v.number}${span}`;
}

/** A multiline slide text: one line per line, the last one optionally in `last`'s color. */
export function Lines({ text, lastColor }: { text: string; lastColor?: string }) {
  const lines = text.split("\n");
  return lines.map((line, i) => (
    <Fragment key={i}>
      {i ? <br /> : null}
      {lastColor && i === lines.length - 1 && lines.length > 1 ? <span style={{ color: lastColor }}>{line}</span> : line}
    </Fragment>
  ));
}

export function Frame({ background, color, children }: { background: string; color: string; children: ReactNode }) {
  return (
    <div style={{ position: "relative", width: SLIDE_W, height: SLIDE_H, overflow: "hidden", background, color, fontFamily: BODY }}>
      {children}
    </div>
  );
}

export function Brand({ sealOnAccent = false }: { sealOnAccent?: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <div style={{
          width: 60, height: 60, borderRadius: 10, display: "grid", placeItems: "center", transform: "rotate(-3deg)",
          background: sealOnAccent ? C.surface : C.accent, color: sealOnAccent ? C.accent : C.surface,
          fontFamily: DISPLAY, fontSize: 32, fontWeight: 700,
        }}>読</div>
        <div style={{ fontFamily: DISPLAY, fontSize: 40, fontWeight: 500 }}>yomiba</div>
      </div>
    </div>
  );
}

/** A real cover, or the site's 読 placeholder when the volume has none yet. */
export function CoverArt({ v, style, border = false, compact = false }: {
  v: Book; style: CSSProperties; border?: boolean; compact?: boolean;
}) {
  const frame: CSSProperties = {
    borderRadius: 10, overflow: "hidden", boxSizing: "border-box", background: C.surface3,
    border: border ? `4px solid ${C.paper}` : undefined, ...style,
  };
  if (!v.cover_url) {
    return (
      <div style={{ ...frame, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8, color: C.faint, textAlign: "center", padding: compact ? 0 : 12 }}>
        <div style={{ fontFamily: DISPLAY, fontSize: compact ? 28 : 64 }}>読</div>
        {compact ? null : <div style={{ fontSize: 20, fontWeight: 700, color: C.ink2 }}>{bookTitle(v)}</div>}
      </div>
    );
  }
  return (
    <div style={frame}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={v.cover_url} alt={bookTitle(v)} style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
    </div>
  );
}

export const SWIPE = (
  <svg aria-hidden width="34" height="34" viewBox="0 0 24 24" fill="none" stroke={C.ink} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14" /><path d="M13 6l6 6-6 6" /></svg>
);

/** Fan positions (left, top, rotation) by how many covers are shown. */
export const FANS: Record<number, [number, number, number][]> = {
  1: [[390, 740, -3]],
  2: [[250, 760, -7], [530, 760, 7]],
  3: [[150, 790, -10], [390, 730, 0], [630, 790, 10]],
  4: [[60, 820, -12], [280, 760, -4], [500, 760, 4], [720, 820, 12]],
  5: [[30, 820, -14], [230, 760, -7], [400, 720, 0], [570, 760, 7], [760, 840, 14]],
};
export const FAN_Z: Record<number, number[]> = { 1: [1], 2: [1, 2], 3: [1, 3, 2], 4: [1, 2, 3, 2], 5: [1, 2, 5, 3, 2] };

export type CoverText = "etiket" | "baslik" | "kaydir";

export const coverTexts = (total: number, weekLabel: string): TextField<CoverText>[] => [
  { id: "etiket", label: "Üst etiket", value: `${weekLabel.toLocaleUpperCase("tr-TR")} · YAYIN TAKVİMİ` },
  { id: "baslik", label: "Başlık (son satır renkli)", value: `Bu hafta\n${total} yeni cilt\nraflarda.`, multiline: true },
  { id: "kaydir", label: "Kaydır düğmesi", value: "Kaydır, hepsini gör" },
];

export function CoverSlide({ fan, tx }: { fan: InstagramVolume[]; tx: Record<CoverText, string> }) {
  const spots = FANS[fan.length] ?? [];
  return (
    <Frame background={C.ink} color={C.paper}>
      <div aria-hidden style={{ position: "absolute", right: -120, top: -120, width: 620, height: 620, borderRadius: "50%", backgroundImage: "radial-gradient(circle, rgba(184,50,27,0.55) 3px, transparent 3.5px)", backgroundSize: "22px 22px" }} />
      <div aria-hidden style={{ position: "absolute", left: 72, top: 330, fontFamily: DISPLAY, fontSize: 360, fontWeight: 900, lineHeight: 1, color: "rgba(247,242,231,0.05)" }}>新刊</div>
      <div style={{ position: "absolute", left: 72, right: 72, top: 64 }}><Brand /></div>
      <div style={{ position: "absolute", left: 72, right: 72, top: 196, display: "flex", flexDirection: "column", gap: 22 }}>
        {tx.etiket ? (
          <div style={{ alignSelf: "flex-start", background: C.accent, color: C.surface, fontSize: 24, fontWeight: 800, letterSpacing: 3, padding: "10px 18px", transform: "rotate(-1.5deg)" }}>
            {tx.etiket}
          </div>
        ) : null}
        <h1 style={{ margin: 0, fontFamily: DISPLAY, fontSize: 128, lineHeight: 0.92, fontWeight: 900, letterSpacing: -3 }}>
          <Lines text={tx.baslik} lastColor={C.accentSoft} />
        </h1>
      </div>
      {fan.map((v, i) => {
        const [left, top, rot] = spots[i];
        return (
          <CoverArt key={v.id} v={v} border style={{
            position: "absolute", left, top, width: 300, height: 450, transform: `rotate(${rot}deg)`,
            zIndex: FAN_Z[fan.length][i], boxShadow: "0 24px 50px rgba(0,0,0,0.55)",
          }} />
        );
      })}
      <div style={{ position: "absolute", right: 72, bottom: 64, zIndex: 10, display: "flex", alignItems: "center", gap: 14, background: C.paper, color: C.ink, borderRadius: 999, padding: "16px 28px", fontSize: 26, fontWeight: 800 }}>
        {tx.kaydir} {SWIPE}
      </div>
    </Frame>
  );
}

const MAX_STORE_ROWS = 6;

export type CompareText = "etiket" | "baslik" | "alt" | "tablo" | "not" | "link";

/** One volume's price at every store (the launch post's example). */
export function CompareSlide({ v, others, tx }: {
  v: LaunchVolume; others: LaunchVolume[]; tx: Record<CompareText, string>;
}) {
  const offers = v.offers.length > MAX_STORE_ROWS ? v.offers.slice(0, MAX_STORE_ROWS - 1) : v.offers;
  const hidden = v.offers.length - offers.length;
  const max = Math.max(...offers.map((o) => o.price), 1);
  const spread = v.offers.length >= 2 ? v.offers[v.offers.length - 1].price - v.offers[0].price : null;
  return (
    <Frame background={C.paper} color={C.ink}>
      <div style={{ position: "absolute", inset: "64px 72px", display: "flex", flexDirection: "column", gap: 40 }}>
        <Brand />
        <div style={{ display: "flex", gap: 48, alignItems: "center" }}>
          <div style={{ position: "relative", flexShrink: 0 }}>
            <div aria-hidden style={{ position: "absolute", left: -36, top: -30, width: 260, height: 260, backgroundImage: "radial-gradient(circle, rgba(31,27,22,0.22) 3px, transparent 3.5px)", backgroundSize: "18px 18px" }} />
            <CoverArt v={v} style={{ position: "relative", width: 340, height: 510, transform: "rotate(-3deg)", boxShadow: "0 20px 40px rgba(31,27,22,0.3)" }} />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 18, minWidth: 0 }}>
            <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: 3, color: C.indigo }}>{tx.etiket}</div>
            <h2 style={{ margin: 0, fontFamily: DISPLAY, fontSize: tx.baslik.length > 18 ? 68 : 80, lineHeight: 0.95, fontWeight: 900, letterSpacing: -2 }}>{tx.baslik}</h2>
            <div style={{ fontSize: 26, color: C.muted }}>{tx.alt}</div>
            <div style={{ marginTop: 12, background: C.ink, color: C.paper, borderRadius: 16, padding: "22px 26px", display: "flex", flexDirection: "column", gap: 4, transform: "rotate(1deg)" }}>
              <div style={{ fontSize: 22, fontWeight: 600, color: "rgba(247,242,231,0.7)" }}>
                {spread !== null ? "Mağazalar arasındaki fark" : v.offers.length ? "Şu an tek mağazada" : "Fiyat"}
              </div>
              <div style={{ fontFamily: DISPLAY, fontSize: 64, fontWeight: 900, lineHeight: 1, color: C.accentSoft }}>
                {spread !== null ? formatPrice(spread) : v.offers.length ? formatPrice(v.offers[0].price) : "Yakında"}
              </div>
            </div>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ fontFamily: DISPLAY, fontSize: 36, fontWeight: 700 }}>{tx.tablo}</div>
          {offers.length === 0 ? (
            <div style={{ fontSize: 26, color: C.muted }}>Henüz hiçbir mağazada stokta değil. Satışa çıkınca sitede görünecek.</div>
          ) : offers.map((o, i) => (
            <div key={o.store_code} style={{ display: "flex", alignItems: "center", gap: 20, fontSize: 26 }}>
              <div style={{ width: 210, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{o.store}</div>
              <div style={{ flex: 1, height: 40, borderRadius: 8, background: C.surface3, overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${Math.round((o.price / max) * 100)}%`, background: i === 0 ? C.accent : C.faint, borderRadius: 8, display: "flex", alignItems: "center", paddingLeft: 14, boxSizing: "border-box", color: C.surface, fontSize: 18, fontWeight: 800, letterSpacing: 2 }}>
                  {i === 0 ? "EN UCUZ" : ""}
                </div>
              </div>
              <div style={{ width: 170, textAlign: "right", fontWeight: 800 }}>{formatPrice(o.price)}</div>
            </div>
          ))}
          {hidden > 0 ? <div style={{ fontSize: 22, color: C.muted }}>+{hidden} mağaza daha</div> : null}
        </div>
        <div style={{ marginTop: "auto", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24, borderTop: `2px solid ${C.line}`, paddingTop: 24 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {others.slice(0, 7).map((o) => (
              <CoverArt key={o.id} v={o} compact style={{ width: 52, height: 78, borderRadius: 4, boxShadow: "0 3px 8px rgba(31,27,22,0.2)" }} />
            ))}
            {tx.not ? <div style={{ fontSize: 24, fontWeight: 700, color: C.ink2, marginLeft: 8 }}>{tx.not}</div> : null}
          </div>
          <div style={{ fontSize: 26, fontWeight: 800, color: C.accent }}>{tx.link}</div>
        </div>
      </div>
    </Frame>
  );
}

const MONTH = new Intl.DateTimeFormat("tr-TR", { month: "long", timeZone: "UTC" });
const WEEKDAY_ONLY = new Intl.DateTimeFormat("tr-TR", { weekday: "long", timeZone: "UTC" });

export type VolumeText = "etiket" | "baslik" | "alt" | "not" | "link";

export const volumeTexts = (v: InstagramVolume, others: number): TextField<VolumeText>[] => [
  { id: "etiket", label: "Üst etiket", value: "BU HAFTA RAFLARDA" },
  { id: "baslik", label: "Cilt adı", value: bookTitle(v) },
  { id: "alt", label: "Alt satır", value: v.author ? `${v.author} · ${v.publisher}` : v.publisher },
  { id: "not", label: "Alt not", value: others ? `+${others} cilt daha` : "" },
  { id: "link", label: "Link", value: "yomiba.net/takvim" },
];

/** One featured volume of the week: big cover, release day and credits.
 * No prices: the weekly post should not read as an ad. */
export function VolumeSlide({ v, others, tx }: {
  v: InstagramVolume; others: InstagramVolume[]; tx: Record<VolumeText, string>;
}) {
  const date = isoDate(v.release_date);
  const title = tx.baslik;
  return (
    <Frame background={C.paper} color={C.ink}>
      <div style={{ position: "absolute", inset: "64px 72px", display: "flex", flexDirection: "column", gap: 40 }}>
        <Brand />
        <div style={{ display: "flex", gap: 56, alignItems: "center", height: 690 }}>
          <div style={{ position: "relative", flexShrink: 0 }}>
            <div aria-hidden style={{ position: "absolute", left: -40, top: -36, width: 300, height: 300, backgroundImage: "radial-gradient(circle, rgba(31,27,22,0.22) 3px, transparent 3.5px)", backgroundSize: "18px 18px" }} />
            <CoverArt v={v} style={{ position: "relative", width: 460, height: 690, transform: "rotate(-3deg)", boxShadow: "0 24px 48px rgba(31,27,22,0.32)" }} />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 36, minWidth: 0, flex: 1 }}>
            <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: 3, color: C.indigo }}>{tx.etiket}</div>
            <div style={{ width: 250, height: 250, borderRadius: "50%", background: C.accent, color: C.surface, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", transform: "rotate(-8deg)", boxShadow: `0 0 0 8px ${C.paper}, 0 0 0 12px ${C.accent}` }}>
              <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: 2 }}>{WEEKDAY_ONLY.format(date).toLocaleUpperCase("tr-TR")}</div>
              <div style={{ fontFamily: DISPLAY, fontSize: 110, fontWeight: 900, lineHeight: 1 }}>{date.getUTCDate()}</div>
              <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: 2 }}>{MONTH.format(date).toLocaleUpperCase("tr-TR")}</div>
            </div>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <h2 style={{ margin: 0, fontFamily: DISPLAY, fontSize: title.length > 18 ? 76 : 96, lineHeight: 0.95, fontWeight: 900, letterSpacing: -2 }}>{title}</h2>
          <div style={{ fontSize: 30, color: C.muted }}>{tx.alt}</div>
        </div>
        <div style={{ marginTop: "auto", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24, borderTop: `2px solid ${C.line}`, paddingTop: 24 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {others.slice(0, 7).map((o) => (
              <CoverArt key={o.id} v={o} compact style={{ width: 52, height: 78, borderRadius: 4, boxShadow: "0 3px 8px rgba(31,27,22,0.2)" }} />
            ))}
            {tx.not ? <div style={{ fontSize: 24, fontWeight: 700, color: C.ink2, marginLeft: 8 }}>{tx.not}</div> : null}
          </div>
          <div style={{ fontSize: 26, fontWeight: 800, color: C.accent }}>{tx.link}</div>
        </div>
      </div>
    </Frame>
  );
}

export const LIST_MAX = 8;

export type ListText = "etiket" | "baslik" | "not" | "link";

export const listTexts = (shown: number, total: number, weekLabel: string): TextField<ListText>[] => [
  { id: "etiket", label: "Üst etiket", value: `${weekLabel.toLocaleUpperCase("tr-TR")} · ${total} CİLT` },
  { id: "baslik", label: "Başlık", value: total > shown ? "Haftanın listesi" : "Haftanın tam listesi" },
  { id: "not", label: "Alt not", value: total > shown ? `+${total - shown} cilt daha takvimde` : "Haftanın tüm çıkışları takvimde" },
  { id: "link", label: "Link", value: "yomiba.net/takvim" },
];

export function ListSlide({ volumes, tx }: { volumes: InstagramVolume[]; tx: Record<ListText, string> }) {
  return (
    <Frame background={C.paper} color={C.ink}>
      <div style={{ position: "absolute", inset: "64px 72px", display: "flex", flexDirection: "column", gap: 36 }}>
        <Brand />
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: 3, color: C.indigo }}>{tx.etiket}</div>
          <h2 style={{ margin: 0, fontFamily: DISPLAY, fontSize: 80, lineHeight: 0.95, fontWeight: 900, letterSpacing: -2 }}>
            <Lines text={tx.baslik} />
          </h2>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "18px 24px" }}>
          {volumes.map((v) => (
            <div key={v.id} style={{ width: 456, boxSizing: "border-box", display: "flex", gap: 18, alignItems: "center", background: C.surface, border: `2px solid ${C.line}`, borderRadius: 14, padding: 14 }}>
              <CoverArt v={v} compact style={{ width: 100, height: 150, flexShrink: 0, borderRadius: 6, boxShadow: "0 4px 10px rgba(31,27,22,0.2)" }} />
              <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}>
                <div style={{ fontSize: 18, fontWeight: 700, color: C.faint }}>{weekdayLabel(v.release_date)}</div>
                <div style={{ fontFamily: DISPLAY, fontSize: 28, fontWeight: 700, lineHeight: 1.05 }}>{bookTitle(v)}</div>
                <div style={{ fontSize: 20, color: C.muted }}>{v.publisher}</div>
              </div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: "auto", display: "flex", alignItems: "center", justifyContent: "space-between", borderTop: `2px solid ${C.line}`, paddingTop: 22 }}>
          <div style={{ fontSize: 22, color: C.muted }}>{tx.not}</div>
          <div style={{ fontSize: 26, fontWeight: 800, color: C.accent }}>{tx.link}</div>
        </div>
      </div>
    </Frame>
  );
}

export type CtaText = "baslik" | "adim1" | "adim1Metin" | "adim2" | "adim2Metin" | "adim3" | "adim3Metin"
  | "linkUst" | "link" | "kaydet";

export const ctaTexts = (baslik = "Yeni ciltleri\nkaçırma."): TextField<CtaText>[] => [
  { id: "baslik", label: "Başlık", value: baslik, multiline: true },
  { id: "adim1", label: "1. kutu başlığı", value: "Takvime bak" },
  { id: "adim1Metin", label: "1. kutu metni", value: "Türkiye’de çıkan her cilt, gün gün" },
  { id: "adim2", label: "2. kutu başlığı", value: "Koleksiyonunu tut" },
  { id: "adim2Metin", label: "2. kutu metni", value: "Elindeki ciltleri işaretle, serini takip et" },
  { id: "adim3", label: "3. kutu başlığı", value: "İstek listene ekle" },
  { id: "adim3Metin", label: "3. kutu metni", value: "Almak istediklerin tek yerde" },
  { id: "linkUst", label: "Link üstü", value: "Link profilde" },
  { id: "link", label: "Link", value: "yomiba.net" },
  { id: "kaydet", label: "Sağ alt düğme", value: "Kaydet, lazım olur" },
];

export function CtaSlide({ tx }: { tx: Record<CtaText, string> }) {
  const steps = ([1, 2, 3] as const).map((n) => ({ title: tx[`adim${n}`], text: tx[`adim${n}Metin`] }))
    .filter((s) => s.title || s.text);
  return (
    <Frame background={C.accent} color={C.surface}>
      <div aria-hidden style={{ position: "absolute", left: "50%", top: "40%", width: 2400, height: 2400, marginLeft: -1200, marginTop: -1200, background: "repeating-conic-gradient(from 0deg, rgba(255,253,248,0.09) 0deg 2deg, transparent 2deg 9deg)" }} />
      <div style={{ position: "absolute", inset: "64px 72px", display: "flex", flexDirection: "column", gap: 44 }}>
        <Brand sealOnAccent />
        <h2 style={{ margin: "40px 0 0", fontFamily: DISPLAY, fontSize: 116, lineHeight: 0.95, fontWeight: 900, letterSpacing: -3 }}>
          <Lines text={tx.baslik} />
        </h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          {steps.map((s, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 26, background: C.surface, color: C.ink, borderRadius: 18, padding: "24px 30px", boxShadow: `8px 8px 0 ${C.ink}` }}>
              <div style={{ width: 64, height: 64, flexShrink: 0, borderRadius: "50%", background: C.ink, color: C.surface, display: "grid", placeItems: "center", fontFamily: DISPLAY, fontSize: 34, fontWeight: 900 }}>{i + 1}</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <div style={{ fontSize: 32, fontWeight: 800 }}>{s.title}</div>
                <div style={{ fontSize: 24, color: C.muted }}>{s.text}</div>
              </div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: "auto", display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ fontSize: 24, fontWeight: 600, color: "rgba(255,253,248,0.8)" }}>{tx.linkUst}</div>
            <div style={{ fontFamily: DISPLAY, fontSize: 60, fontWeight: 900, lineHeight: 1 }}>{tx.link}</div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, border: `3px solid ${C.surface}`, borderRadius: 999, padding: "14px 24px", fontSize: 24, fontWeight: 800 }}>
            <svg aria-hidden width="30" height="30" viewBox="0 0 24 24" fill="none" stroke={C.surface} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M6 3h12v18l-6-4-6 4z" /></svg>
            {tx.kaydet}
          </div>
        </div>
      </div>
    </Frame>
  );
}
