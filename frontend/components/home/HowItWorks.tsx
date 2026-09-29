import Link from "next/link";
import { Badge, SectionHeading } from "@/components/ui";

const STEPS = [
  {
    no: "一",
    title: "Ara",
    text: "Seriyi Türkçe ya da orijinal adıyla ara. Katalog, Türkiye'de yayımlanan baskıları yayınevi yayınevi tanır.",
  },
  {
    no: "二",
    title: "Karşılaştır",
    text: "Her cildin fiyatını mağazalar arasında yan yana gör. Stokta olanlar önde, en düşük fiyat işaretli.",
  },
  {
    no: "三",
    title: "Takip et",
    text: "Sahip olduklarını ve eksiklerini işaretle, istek listesi tut, hedef fiyatına alarm kur.",
  },
];

/** "How it works" + the price-alert mini feature + the membership CTA. */
export function HowItWorks({ signedIn }: { signedIn: boolean }) {
  return (
    <section aria-labelledby="nasil-title" className="space-y-8">
      <SectionHeading id="nasil-title" folio="04" eyebrow="Yomiba nasıl çalışır?" title="Üç adımda doğru fiyat" />

      <ol className="grid gap-6 sm:grid-cols-3">
        {STEPS.map((s) => (
          <li key={s.title} className="space-y-2">
            <span aria-hidden className="font-display text-3xl text-accent">
              {s.no}
            </span>
            <h3 className="text-xl font-semibold text-ink">{s.title}</h3>
            <p className="text-sm leading-relaxed text-muted">{s.text}</p>
          </li>
        ))}
      </ol>

      <div className="grid overflow-hidden rounded-2xl border border-line bg-surface shadow-card md:grid-cols-[1.3fr_1fr]">
        <div className="space-y-4 p-6 sm:p-8">
          <p className="eyebrow">Fiyat alarmı</p>
          <h3 className="text-2xl font-semibold text-ink sm:text-3xl">Beklediğin fiyatı kaydet.</h3>
          <p className="max-w-lg text-sm leading-relaxed text-muted sm:text-base">
            Her cilt için bir hedef fiyat belirle; koleksiyonundaki eksikleri ve istek listeni aynı
            yerde tut. Alarmlar şimdilik hedefini saklıyor, bildirimler yakında geliyor.
          </p>
          <div className="flex flex-wrap gap-3 pt-1">
            <Link
              href={signedIn ? "/collection" : "/register"}
              className="inline-flex min-h-11 items-center rounded-xl bg-ink px-4 font-semibold text-paper transition-colors hover:bg-accent"
            >
              {signedIn ? "Koleksiyonuna git" : "Ücretsiz hesap oluştur"}
            </Link>
            {!signedIn && (
              <Link
                href="/login"
                className="inline-flex min-h-11 items-center rounded-xl px-2 font-semibold text-ink-2 hover:text-accent"
              >
                Zaten üyeyim
              </Link>
            )}
          </div>
        </div>
        {/* A labelled sample of the alert panel, not real data. */}
        <div className="screentone relative flex items-center justify-center border-t border-line p-6 md:border-t-0 md:border-l">
          <figure className="w-full max-w-xs rounded-xl border border-line bg-surface p-4 shadow-lift">
            <figcaption className="mb-3 flex items-center justify-between">
              <span className="eyebrow">Örnek</span>
              <Badge tone="alert" dot>
                Alarm kuruldu
              </Badge>
            </figcaption>
            <p className="text-sm text-muted">Hedef fiyat</p>
            <p className="tabular font-display text-3xl text-ink">150 ₺</p>
            <div aria-hidden className="mt-4 flex h-12 items-end gap-1.5">
              {[70, 64, 66, 58, 60, 52, 44].map((h, i) => (
                <span
                  key={i}
                  className={`flex-1 rounded-sm ${i === 6 ? "bg-accent" : "bg-surface-3"}`}
                  style={{ height: `${h}%` }}
                />
              ))}
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <Badge tone="wish">İstek listesinde</Badge>
              <Badge tone="stock" dot>
                Stokta
              </Badge>
            </div>
          </figure>
        </div>
      </div>
    </section>
  );
}
