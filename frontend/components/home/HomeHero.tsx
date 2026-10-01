/**
 * HomeHero: headline, the search (the page's main job), CTAs and a real
 * "shelf" of popular covers with their actual lowest prices on the right.
 * Nothing on this shelf is illustrative: covers and prices come from /home.
 */

import Link from "next/link";
import { SearchSection } from "@/components/SearchSection";
import { HeroShelf } from "@/components/home/HeroShelf";
import type { HomeFeed } from "@/types";

const NUMBER = new Intl.NumberFormat("tr-TR");

function pickRandom<T>(items: T[], count: number): T[] {
  const pool = [...items];
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  return pool.slice(0, count);
}

export function HomeHero({ feed, signedIn }: { feed: HomeFeed | null; signedIn: boolean }) {
  // The page is rendered per request, so each visit shows a different trio
  // from the whole popular pool instead of always the same top three.
  const shelf = pickRandom(
    // Only series someone can buy today (an in-stock price) with a cover.
    (feed?.popular_series ?? []).filter((s) => s.cover_url && s.lowest_price !== null && s.in_stock_offers > 0),
    3,
  );
  const lead = shelf[0];

  return (
    <section id="ara" aria-labelledby="hero-title" className="scroll-mt-28">
      <div className="grid items-center gap-10 lg:grid-cols-[1.25fr_1fr] lg:gap-14">
        <div className="space-y-6">
          <p className="eyebrow">Manga fiyat karşılaştırma · koleksiyon takibi</p>
          <h1
            id="hero-title"
            className="text-[2.35rem] leading-[1.05] font-semibold text-ink sm:text-[3.4rem]"
          >
            Rafına eklenecek bir sonraki cilt,{" "}
            <em className="font-sans font-bold tracking-tight text-accent not-italic">
              en uygun fiyatıyla
            </em>
            .
          </h1>
          <p className="max-w-xl text-[1.05rem] leading-relaxed text-muted">
            Aynı cildin fiyatını Türkiye&apos;deki kitapçılarda yan yana gör, stokta olanı tek
            bakışta bul. Koleksiyonunu tut, istek listeni oluştur, fiyat düşünce haberin olsun.
          </p>

          <SearchSection syncUrl />

          <div className="flex flex-wrap items-center gap-3">
            <Link
              href="#indirimler"
              className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-line-strong bg-surface px-4 font-semibold text-ink shadow-card transition-colors hover:border-ink/40"
            >
              <span aria-hidden className="size-2 rounded-full bg-accent" />
              İndirimleri keşfet
            </Link>
            <Link
              href={signedIn ? "/collection" : "/register"}
              className="inline-flex min-h-11 items-center rounded-xl px-2 font-semibold text-ink-2 underline decoration-line-strong decoration-2 underline-offset-[6px] transition-colors hover:text-accent hover:decoration-accent"
            >
              {signedIn ? "Koleksiyonuna git" : "Koleksiyonunu oluştur"}
            </Link>
          </div>

          {feed && (
            <dl className="flex flex-wrap gap-x-8 gap-y-2 border-t border-line pt-5 text-sm">
              <div>
                <dt className="text-faint">Katalogdaki seri</dt>
                <dd className="tabular font-sans text-xl font-bold text-ink">{NUMBER.format(feed.stats.series)}</dd>
              </div>
              <div>
                <dt className="text-faint">Takip edilen mağaza</dt>
                <dd className="tabular font-sans text-xl font-bold text-ink">{NUMBER.format(feed.stats.stores)}</dd>
              </div>
              <div>
                <dt className="text-faint">Güncel fiyat</dt>
                <dd className="tabular font-sans text-xl font-bold text-ink">{NUMBER.format(feed.stats.offers)}</dd>
              </div>
            </dl>
          )}
        </div>

        {lead && <HeroShelf series={shelf} />}
      </div>
    </section>
  );
}

