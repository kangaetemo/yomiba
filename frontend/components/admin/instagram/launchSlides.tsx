/**
 * Slides of the "site açıldı" announcement carousel. Same size, colors and
 * inline-style rule as the weekly slides (see slides.tsx); the price example
 * slide is the weekly CompareSlide with launch wording.
 */

import type { LaunchStats, LaunchVolume } from "@/services/instagram";
import type { TextField } from "./parts";
import { Brand, C, CoverArt, DISPLAY, FAN_Z, FANS, Frame, Lines, SWIPE } from "./slides";

export const count = (n: number) => n.toLocaleString("tr-TR");

export type LaunchCoverText = "etiket" | "baslik" | "kaydir";

export const launchCoverTexts = (): TextField<LaunchCoverText>[] => [
  { id: "etiket", label: "Üst etiket", value: "YENİ SİTE · YOMİBA.NET AÇILDI" },
  { id: "baslik", label: "Başlık (son satır renkli)", value: "Manga fiyatları\nartık\ntek yerde.", multiline: true },
  { id: "kaydir", label: "Kaydır düğmesi", value: "Kaydır, nasıl çalıştığını gör" },
];

export function LaunchCoverSlide({ fan, stats, tx }: {
  fan: LaunchVolume[]; stats: LaunchStats; tx: Record<LaunchCoverText, string>;
}) {
  const spots = FANS[fan.length] ?? [];
  const figures = [
    [count(stats.series), "seri"],
    [count(stats.volumes), "cilt"],
    [count(stats.stores), "mağaza"],
  ];
  return (
    <Frame background={C.ink} color={C.paper}>
      <div aria-hidden style={{ position: "absolute", right: -120, top: -120, width: 620, height: 620, borderRadius: "50%", backgroundImage: "radial-gradient(circle, rgba(184,50,27,0.55) 3px, transparent 3.5px)", backgroundSize: "22px 22px" }} />
      <div aria-hidden style={{ position: "absolute", left: 60, top: 300, fontFamily: DISPLAY, fontSize: 360, fontWeight: 900, lineHeight: 1, color: "rgba(247,242,231,0.05)" }}>開店</div>
      <div style={{ position: "absolute", left: 72, right: 72, top: 64 }}><Brand /></div>
      <div style={{ position: "absolute", left: 72, right: 72, top: 180, display: "flex", flexDirection: "column", gap: 26 }}>
        {tx.etiket ? (
          <div style={{ alignSelf: "flex-start", background: C.accent, color: C.surface, fontSize: 24, fontWeight: 800, letterSpacing: 3, padding: "10px 18px", transform: "rotate(-1.5deg)" }}>
            {tx.etiket}
          </div>
        ) : null}
        <h1 style={{ margin: 0, fontFamily: DISPLAY, fontSize: 112, lineHeight: 0.92, fontWeight: 900, letterSpacing: -3 }}>
          <Lines text={tx.baslik} lastColor={C.accentSoft} />
        </h1>
        <div style={{ display: "flex", gap: 14 }}>
          {figures.map(([value, label]) => (
            <div key={label} style={{ display: "flex", alignItems: "baseline", gap: 10, border: "2px solid rgba(247,242,231,0.35)", borderRadius: 999, padding: "10px 22px" }}>
              <span style={{ fontFamily: DISPLAY, fontSize: 38, fontWeight: 900 }}>{value}</span>
              <span style={{ fontSize: 24, fontWeight: 700, color: "rgba(247,242,231,0.75)" }}>{label}</span>
            </div>
          ))}
        </div>
      </div>
      {fan.map((v, i) => {
        const [left, top, rot] = spots[i];
        return (
          <CoverArt key={v.id} v={v} border style={{
            position: "absolute", left, top: top + 40, width: 300, height: 450, transform: `rotate(${rot}deg)`,
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

const FEATURES = (stores: number) => [
  { mark: "比", title: "Fiyat karşılaştırma", text: `${count(stores)} mağazanın fiyatı yan yana, en ucuzu en üstte` },
  { mark: "鈴", title: "Fiyat alarmı", text: "Hedef fiyatını yaz, altına inince e-posta gelsin" },
  { mark: "暦", title: "Yayın takvimi", text: "Bu hafta ve bu ay hangi ciltler çıkıyor" },
  { mark: "割", title: "İndirimler", text: "Fiyatı son günlerde düşen ciltler tek listede" },
  { mark: "棚", title: "Koleksiyon ve istek listesi", text: "Elindekileri işaretle, almak istediklerini biriktir" },
];
const FEATURE_N = [1, 2, 3, 4, 5] as const;

export type FeaturesText = "etiket" | "baslik" | `ozellik${(typeof FEATURE_N)[number]}` | `ozellik${(typeof FEATURE_N)[number]}Metin`
  | "not" | "link";

export const featuresTexts = (stats: LaunchStats): TextField<FeaturesText>[] => [
  { id: "etiket", label: "Üst etiket", value: "YOMİBA'DA NELER VAR?" },
  { id: "baslik", label: "Başlık", value: "Cilt almadan\nönce bir bak.", multiline: true },
  ...FEATURES(stats.stores).flatMap((f, i): TextField<FeaturesText>[] => [
    { id: `ozellik${FEATURE_N[i]}`, label: `${i + 1}. kutu başlığı`, value: f.title },
    { id: `ozellik${FEATURE_N[i]}Metin`, label: `${i + 1}. kutu metni`, value: f.text },
  ]),
  { id: "not", label: "Alt not", value: "Ücretsiz. Bakmak için üye olman gerekmez." },
  { id: "link", label: "Link", value: "yomiba.net" },
];

export function FeaturesSlide({ tx }: { tx: Record<FeaturesText, string> }) {
  const features = FEATURES(0).map((f, i) => ({ mark: f.mark, title: tx[`ozellik${FEATURE_N[i]}`], text: tx[`ozellik${FEATURE_N[i]}Metin`] }))
    .filter((f) => f.title || f.text);
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
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {features.map((f, i) => (
            <div key={f.title} style={{ display: "flex", alignItems: "center", gap: 26, background: C.surface, border: `2px solid ${C.line}`, borderRadius: 18, padding: "20px 28px" }}>
              <div style={{
                width: 72, height: 72, flexShrink: 0, borderRadius: 12, display: "grid", placeItems: "center",
                background: i === 0 ? C.accent : C.ink, color: C.surface, fontFamily: DISPLAY, fontSize: 38, fontWeight: 700,
                transform: `rotate(${i % 2 ? 3 : -3}deg)`,
              }}>{f.mark}</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <div style={{ fontSize: 32, fontWeight: 800 }}>{f.title}</div>
                <div style={{ fontSize: 24, color: C.muted }}>{f.text}</div>
              </div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: "auto", display: "flex", alignItems: "center", justifyContent: "space-between", borderTop: `2px solid ${C.line}`, paddingTop: 22 }}>
          <div style={{ fontSize: 24, color: C.muted }}>{tx.not}</div>
          <div style={{ fontSize: 26, fontWeight: 800, color: C.accent }}>{tx.link}</div>
        </div>
      </div>
    </Frame>
  );
}

export type LaunchCtaText = "baslik" | "kutu1" | "kutu1Metin" | "kutu2" | "kutu2Metin" | "kutu3" | "kutu3Metin"
  | "linkUst" | "link" | "kaydet";

export const launchCtaTexts = (): TextField<LaunchCtaText>[] => [
  { id: "baslik", label: "Başlık", value: "Site açıldı.\nGel bir bak.", multiline: true },
  { id: "kutu1", label: "1. kutu başlığı", value: "Takip et" },
  { id: "kutu1Metin", label: "1. kutu metni", value: "Her hafta çıkan ciltleri ve indirimleri burada paylaşacağız" },
  { id: "kutu2", label: "2. kutu başlığı", value: "Bize yaz" },
  { id: "kutu2Metin", label: "2. kutu metni", value: "Eksik seri ya da yanlış fiyat görürsen yorumda veya DM'den söyle" },
  { id: "kutu3", label: "3. kutu başlığı", value: "Arkadaşına gönder" },
  { id: "kutu3Metin", label: "3. kutu metni", value: "Manga alan bir arkadaşın varsa bu postu ona at" },
  { id: "linkUst", label: "Link üstü", value: "Link profilde" },
  { id: "link", label: "Link", value: "yomiba.net" },
  { id: "kaydet", label: "Sağ alt düğme", value: "Kaydet, lazım olur" },
];

export function LaunchCtaSlide({ tx }: { tx: Record<LaunchCtaText, string> }) {
  const cards = ([1, 2, 3] as const).map((n) => [tx[`kutu${n}`], tx[`kutu${n}Metin`]]).filter(([t, x]) => t || x);
  return (
    <Frame background={C.accent} color={C.surface}>
      <div aria-hidden style={{ position: "absolute", left: "50%", top: "40%", width: 2400, height: 2400, marginLeft: -1200, marginTop: -1200, background: "repeating-conic-gradient(from 0deg, rgba(255,253,248,0.09) 0deg 2deg, transparent 2deg 9deg)" }} />
      <div style={{ position: "absolute", inset: "64px 72px", display: "flex", flexDirection: "column", gap: 44 }}>
        <Brand sealOnAccent />
        <h2 style={{ margin: "40px 0 0", fontFamily: DISPLAY, fontSize: 124, lineHeight: 0.95, fontWeight: 900, letterSpacing: -3 }}>
          <Lines text={tx.baslik} />
        </h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          {cards.map(([title, text], i) => (
            <div key={i} style={{ display: "flex", flexDirection: "column", gap: 4, background: C.surface, color: C.ink, borderRadius: 18, padding: "24px 30px", boxShadow: `8px 8px 0 ${C.ink}` }}>
              <div style={{ fontSize: 32, fontWeight: 800 }}>{title}</div>
              <div style={{ fontSize: 24, color: C.muted }}>{text}</div>
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
