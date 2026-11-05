/**
 * Slides of the "Tekrar stokta" post: one per featured volume (big cover and
 * a stamp with how long it was gone) and the list of the period. Same size
 * and inline-style rules as slides.tsx. No prices or store names.
 */

import type { RestockVolume } from "@/services/instagram";
import type { TextField } from "./parts";
import { Brand, C, CoverArt, DISPLAY, Frame, Lines, bookTitle } from "./slides";

export const RESTOCK_LINK = "yomiba.net/tekrar-stokta";

/** The stamp: "3 / HAFTA / ARADAN SONRA", or "UZUN / ARADAN SONRA". */
export function gapStamp(outDays: number | null): { big: string; unit: string } {
  if (outDays === null) return { big: "UZUN", unit: "" };
  if (outDays < 14) return { big: String(outDays), unit: "GÜN" };
  if (outDays < 60) return { big: String(Math.floor(outDays / 7)), unit: "HAFTA" };
  return { big: String(Math.floor(outDays / 30)), unit: "AY" };
}

/** "3 hafta aradan sonra" (lowercase, for list rows and captions). */
export function gapText(outDays: number | null): string {
  const { big, unit } = gapStamp(outDays);
  return unit ? `${big} ${unit.toLocaleLowerCase("tr-TR")} aradan sonra` : "uzun aradan sonra";
}

export type RestockVolumeText = "etiket" | "baslik" | "alt" | "not" | "link";

export const restockVolumeTexts = (v: RestockVolume, others: number): TextField<RestockVolumeText>[] => [
  { id: "etiket", label: "Üst etiket", value: "TEKRAR STOKTA" },
  { id: "baslik", label: "Cilt adı", value: bookTitle(v) },
  { id: "alt", label: "Alt satır", value: v.author ? `${v.author} · ${v.publisher}` : v.publisher },
  { id: "not", label: "Alt not", value: others ? `+${others} cilt daha` : "" },
  { id: "link", label: "Link", value: RESTOCK_LINK },
];

export function RestockVolumeSlide({ v, others, tx }: {
  v: RestockVolume; others: RestockVolume[]; tx: Record<RestockVolumeText, string>;
}) {
  const stamp = gapStamp(v.out_days);
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
              <div style={{ fontFamily: DISPLAY, fontSize: stamp.unit ? 110 : 64, fontWeight: 900, lineHeight: 1 }}>{stamp.big}</div>
              {stamp.unit ? <div style={{ fontSize: 26, fontWeight: 800, letterSpacing: 2 }}>{stamp.unit}</div> : null}
              <div style={{ marginTop: 6, fontSize: 18, fontWeight: 800, letterSpacing: 2 }}>ARADAN SONRA</div>
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

export const RESTOCK_LIST_MAX = 8;

export type RestockListText = "etiket" | "baslik" | "not" | "link";

export const restockListTexts = (shown: number, total: number, period: string): TextField<RestockListText>[] => [
  { id: "etiket", label: "Üst etiket", value: `${period.toLocaleUpperCase("tr-TR")} · ${total} CİLT` },
  { id: "baslik", label: "Başlık", value: "Yeniden raflarda" },
  { id: "not", label: "Alt not", value: total > shown ? `+${total - shown} cilt daha sitede` : "Hangi mağazada olduğu sitede" },
  { id: "link", label: "Link", value: RESTOCK_LINK },
];

export function RestockListSlide({ volumes, tx }: { volumes: RestockVolume[]; tx: Record<RestockListText, string> }) {
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
                <div style={{ fontSize: 18, fontWeight: 700, color: C.accent }}>{gapText(v.out_days)}</div>
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
