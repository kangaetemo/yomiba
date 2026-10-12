import type { Metadata } from "next";
import Link from "next/link";
import { Badge, Cover, formatDate, formatTL, volumeTitle } from "@/components/ui";
import { volumePath } from "@/lib/paths";
import { TIME_ZONE } from "@/lib/time";
import { getReleaseCalendar } from "@/services/catalog";
import type { NewVolume } from "@/types";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Manga yayın takvimi",
  description: "Türkiye'de yayımlanan manga ciltlerini çıkış tarihlerine göre takip et, önceki aylara göz at ve fiyatları karşılaştır.",
};

const MONTH_PATTERN = /^[1-9]\d{3}-(0[1-9]|1[0-2])$/;
const WEEKDAYS = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"];
const MONTH_LABEL = new Intl.DateTimeFormat("tr-TR", { month: "long", year: "numeric", timeZone: "UTC" });
const BUTTON = "inline-flex min-h-11 items-center justify-center rounded-lg border border-line bg-surface px-3 text-sm font-semibold text-ink-2 hover:border-line-strong hover:text-accent";

function currentMonth(): string {
  const parts = new Intl.DateTimeFormat("en", { year: "numeric", month: "2-digit", timeZone: TIME_ZONE }).formatToParts(new Date());
  return `${parts.find((p) => p.type === "year")!.value}-${parts.find((p) => p.type === "month")!.value}`;
}

function adjacentMonth(year: number, month: number, step: number): string | null {
  const date = new Date(Date.UTC(year, month - 1 + step, 1));
  const nextYear = date.getUTCFullYear();
  if (nextYear < 1000 || nextYear > 9999) return null;
  return `${nextYear}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
}

export default async function CalendarPage({
  searchParams,
}: {
  searchParams: Promise<{ ay?: string | string[] }>;
}) {
  const { ay } = await searchParams;
  const thisMonth = currentMonth();
  const month = typeof ay === "string" && MONTH_PATTERN.test(ay) ? ay : thisMonth;
  const [year, monthNumber] = month.split("-").map(Number);
  const monthLabel = MONTH_LABEL.format(new Date(Date.UTC(year, monthNumber - 1, 1)));
  const previous = adjacentMonth(year, monthNumber, -1);
  const next = adjacentMonth(year, monthNumber, 1);
  const feed = await getReleaseCalendar(month).catch(() => null);
  const groups = new Map<string, NewVolume[]>();
  for (const volume of feed?.volumes ?? []) {
    const day = groups.get(volume.release_date) ?? [];
    day.push(volume);
    groups.set(volume.release_date, day);
  }
  const firstWeekday = (new Date(Date.UTC(year, monthNumber - 1, 1)).getUTCDay() + 6) % 7;
  const daysInMonth = new Date(Date.UTC(year, monthNumber, 0)).getUTCDate();
  const cells = Math.ceil((firstWeekday + daysInMonth) / 7) * 7;

  return (
    <div className="space-y-8">
      <nav aria-label="Konum" className="text-sm text-muted">
        <Link href="/#yeni" className="inline-flex min-h-11 items-center hover:text-accent">← Yeni çıkan ciltler</Link>
      </nav>
      <header className="space-y-3">
        <div className="rule" aria-hidden />
        <p className="eyebrow">Ay ay manga</p>
        <h1 className="text-3xl font-semibold text-ink sm:text-4xl">Yayın takvimi</h1>
        <p className="max-w-2xl text-sm text-muted sm:text-base">
          Türkiye&apos;de çıkan ciltler, yayın tarihleriyle bir arada. Bir gün seç, o günün ciltlerine göz at.
        </p>
      </header>

      <section aria-labelledby="takvim-ay" className="overflow-hidden rounded-xl border border-line bg-surface shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-line p-4 sm:p-5">
          <div className="space-y-1">
            <h2 id="takvim-ay" className="text-xl font-semibold capitalize text-ink sm:text-2xl">{monthLabel}</h2>
            {feed && <p className="text-sm text-muted">{feed.volumes.length} cilt · {groups.size} yayın günü</p>}
          </div>
          <nav aria-label="Ay seçimi" className="flex flex-wrap items-center gap-2">
            {previous && <Link href={`/takvim?ay=${previous}`} className={BUTTON} aria-label="Önceki ay">←</Link>}
            <Link href={`/takvim?ay=${thisMonth}`} className={BUTTON}>Bu ay</Link>
            {next && <Link href={`/takvim?ay=${next}`} className={BUTTON} aria-label="Sonraki ay">→</Link>}
          </nav>
          <form action="/takvim" method="get" className="flex w-full flex-wrap items-center gap-2 sm:w-auto">
            <label htmlFor="takvim-month" className="text-sm text-muted">Aya git</label>
            <input id="takvim-month" name="ay" type="month" min="1000-01" max="9999-12" defaultValue={month} key={month} required className="min-h-11 min-w-0 rounded-lg border border-line bg-paper px-2 text-sm text-ink" />
            <button type="submit" className={BUTTON}>Göster</button>
          </form>
        </div>

        {feed === null ? (
          <div role="status" className="space-y-3 p-6 text-sm text-muted">
            <p>Takvim şu an yüklenemedi. Biraz sonra tekrar dene.</p>
            <Link href={`/takvim?ay=${month}`} className={BUTTON}>Tekrar dene</Link>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-7 border-b border-line bg-paper/60 text-center text-xs font-semibold text-muted">
              {WEEKDAYS.map((day) => <span key={day} className="py-3">{day}</span>)}
            </div>
            <ol aria-label={`${monthLabel} yayın günleri`} className="grid grid-cols-7 gap-px bg-line">
              {Array.from({ length: cells }, (_, index) => {
                const day = index - firstWeekday + 1;
                if (day < 1 || day > daysInMonth) return <li key={index} aria-hidden className="min-h-20 bg-paper/60 sm:min-h-24" />;
                const iso = `${month}-${String(day).padStart(2, "0")}`;
                const count = groups.get(iso)?.length ?? 0;
                const isToday = iso === feed.today;
                const cellClass = `flex min-h-20 flex-col items-center justify-center gap-1 p-1 text-sm sm:min-h-24 ${count ? "bg-new-soft text-new hover:bg-surface-3" : "bg-surface text-muted"}`;
                const contents = <><time dateTime={iso} className={`tabular grid size-7 place-items-center rounded-full ${isToday ? "bg-accent font-semibold text-on-accent" : ""}`}>{day}</time>{count > 0 && <span className="text-[0.65rem] font-semibold sm:text-xs">{count} cilt</span>}</>;
                return (
                  <li key={iso}>
                    {count > 0 ? (
                      <a href={`#gun-${iso}`} className={cellClass} aria-label={`${formatDate(iso)}: ${count} cilt`} aria-current={isToday ? "date" : undefined}>{contents}</a>
                    ) : <div className={cellClass} aria-current={isToday ? "date" : undefined}>{contents}</div>}
                  </li>
                );
              })}
            </ol>
          </>
        )}
      </section>

      {feed && (groups.size === 0 ? (
        <div className="space-y-3 rounded-xl border border-dashed border-line-strong bg-surface/70 p-6 text-sm text-muted">
          <p>Bu ay için kayıtlı yayın tarihi yok.</p>
          {feed.latest_month && feed.latest_month !== month && <Link href={`/takvim?ay=${feed.latest_month}`} className={BUTTON}>Son çıkan ciltlere git →</Link>}
        </div>
      ) : (
        <div className="space-y-8">
          {[...groups].map(([date, volumes]) => (
            <section key={date} id={`gun-${date}`} aria-labelledby={`baslik-${date}`} className="scroll-mt-40 space-y-4">
              <div className="flex flex-wrap items-baseline gap-3 border-b border-line pb-3">
                <h2 id={`baslik-${date}`} className="text-xl font-semibold text-ink"><time dateTime={date}>{formatDate(date)}</time></h2>
                <span className="text-sm text-muted">{volumes.length} cilt</span>
                {date > feed.today && <Badge tone="new">Yakında</Badge>}
              </div>
              <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {volumes.map((volume) => (
                  <li key={volume.id}>
                    <Link href={volumePath(volume.series_slug, volume.number)} className="group flex h-full min-w-0 gap-4 rounded-xl border border-line bg-surface p-3.5 shadow-card hover:border-line-strong hover:shadow-lift">
                      <Cover url={volume.cover_url} alt="" className="w-16 self-start sm:w-20" />
                      <div className="flex min-w-0 flex-1 flex-col gap-1">
                        <h3 className="line-clamp-2 text-base font-semibold text-ink group-hover:text-accent">{volume.series_title}</h3>
                        <p className="text-sm text-ink-2">{volumeTitle(volume.number, volume.covers_from, volume.covers_to)}</p>
                        <p className="truncate text-xs text-muted">{volume.publisher}</p>
                        <p className="mt-auto pt-2 text-sm font-semibold text-ink">
                          {volume.lowest_price === null ? <span className="text-xs font-normal text-muted">Henüz satış fiyatı yok</span> : <><span className="tabular">{formatTL(volume.lowest_price)}</span><span className="ml-2 text-xs font-normal text-muted">en düşük</span></>}
                        </p>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      ))}
      <p className="text-xs leading-relaxed text-muted">Tarihler katalogdaki Türkiye yayın tarihleridir. Yayın tarihi bilinmeyen ciltler listelenmez; ileri tarihler değişebilir.</p>
    </div>
  );
}
