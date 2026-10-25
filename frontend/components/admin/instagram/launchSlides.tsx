/**
 * Slides of the "site açıldı" announcement carousel. Same size, colors and
 * inline-style rule as the weekly slides (see slides.tsx); the price example
 * slide is the weekly CompareSlide with launch wording.
 */

import type { LaunchStats, LaunchVolume } from "@/services/instagram";
import { Brand, C, CoverArt, DISPLAY, FAN_Z, FANS, Frame, SWIPE } from "./slides";

export const count = (n: number) => n.toLocaleString("tr-TR");

export function LaunchCoverSlide({ fan, stats, page }: { fan: LaunchVolume[]; stats: LaunchStats; page: string }) {
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
      <div style={{ position: "absolute", left: 72, right: 72, top: 64 }}><Brand page={page} dark /></div>
      <div style={{ position: "absolute", left: 72, right: 72, top: 180, display: "flex", flexDirection: "column", gap: 26 }}>
        <div style={{ alignSelf: "flex-start", background: C.accent, color: C.surface, fontSize: 24, fontWeight: 800, letterSpacing: 3, padding: "10px 18px", transform: "rotate(-1.5deg)" }}>
          YENİ SİTE · YOMİBA.NET AÇILDI
        </div>
        <h1 style={{ margin: 0, fontFamily: DISPLAY, fontSize: 112, lineHeight: 0.92, fontWeight: 900, letterSpacing: -3 }}>
          Manga fiyatları<br />artık<br /><span style={{ color: C.accentSoft }}>tek yerde.</span>
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
        Kaydır, nasıl çalıştığını gör {SWIPE}
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

export function FeaturesSlide({ stats, page }: { stats: LaunchStats; page: string }) {
  return (
    <Frame background={C.paper} color={C.ink}>
      <div style={{ position: "absolute", inset: "64px 72px", display: "flex", flexDirection: "column", gap: 36 }}>
        <Brand page={page} />
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: 3, color: C.indigo }}>YOMİBA&apos;DA NELER VAR?</div>
          <h2 style={{ margin: 0, fontFamily: DISPLAY, fontSize: 80, lineHeight: 0.95, fontWeight: 900, letterSpacing: -2 }}>
            Cilt almadan<br />önce bir bak.
          </h2>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {FEATURES(stats.stores).map((f, i) => (
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
          <div style={{ fontSize: 24, color: C.muted }}>Ücretsiz. Bakmak için üye olman gerekmez.</div>
          <div style={{ fontSize: 26, fontWeight: 800, color: C.accent }}>yomiba.net</div>
        </div>
      </div>
    </Frame>
  );
}

export function LaunchCtaSlide({ page }: { page: string }) {
  return (
    <Frame background={C.accent} color={C.surface}>
      <div aria-hidden style={{ position: "absolute", left: "50%", top: "40%", width: 2400, height: 2400, marginLeft: -1200, marginTop: -1200, background: "repeating-conic-gradient(from 0deg, rgba(255,253,248,0.09) 0deg 2deg, transparent 2deg 9deg)" }} />
      <div style={{ position: "absolute", inset: "64px 72px", display: "flex", flexDirection: "column", gap: 44 }}>
        <Brand page={page} dark sealOnAccent />
        <h2 style={{ margin: "40px 0 0", fontFamily: DISPLAY, fontSize: 124, lineHeight: 0.95, fontWeight: 900, letterSpacing: -3 }}>
          Site açıldı.<br />Gel bir bak.
        </h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          {[
            ["Takip et", "Her hafta çıkan ciltleri ve indirimleri burada paylaşacağız"],
            ["Bize yaz", "Eksik seri ya da yanlış fiyat görürsen yorumda veya DM'den söyle"],
            ["Arkadaşına gönder", "Manga alan bir arkadaşın varsa bu postu ona at"],
          ].map(([title, text]) => (
            <div key={title} style={{ display: "flex", flexDirection: "column", gap: 4, background: C.surface, color: C.ink, borderRadius: 18, padding: "24px 30px", boxShadow: `8px 8px 0 ${C.ink}` }}>
              <div style={{ fontSize: 32, fontWeight: 800 }}>{title}</div>
              <div style={{ fontSize: 24, color: C.muted }}>{text}</div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: "auto", display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ fontSize: 24, fontWeight: 600, color: "rgba(255,253,248,0.8)" }}>Link profilde</div>
            <div style={{ fontFamily: DISPLAY, fontSize: 60, fontWeight: 900, lineHeight: 1 }}>yomiba.net</div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, border: `3px solid ${C.surface}`, borderRadius: 999, padding: "14px 24px", fontSize: 24, fontWeight: 800 }}>
            <svg aria-hidden width="30" height="30" viewBox="0 0 24 24" fill="none" stroke={C.surface} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M6 3h12v18l-6-4-6 4z" /></svg>
            Kaydet, lazım olur
          </div>
        </div>
      </div>
    </Frame>
  );
}
