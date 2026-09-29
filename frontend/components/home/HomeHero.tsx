/**
 * HomeHero: headline, the search (the page's main job), CTAs and a real
 * "shelf" of popular covers with their actual lowest prices on the right.
 * Nothing on this shelf is illustrative: covers and prices come from /home.
 */

import Link from "next/link";
import { SearchSection } from "@/components/SearchSection";
import { Cover, formatTL } from "@/components/ui";
import type { HomeFeed } from "@/types";

const NUMBER = new Intl.NumberFormat("tr-TR");

export function HomeHero({ feed, signedIn }: { feed: HomeFeed | null; signedIn: boolean }) {
  const shelf = (feed?.popular_series ?? []).filter((s) => s.cover_url).slice(0, 3);
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
            <em className="font-medium text-accent not-italic [font-variation-settings:'SOFT'_100]">
              en uygun fiyatıyla
            </em>
            .
          </h1>
          <p className="max-w-xl text-[1.05rem] leading-relaxed text-muted">
            Aynı cildin fiyatını Türkiye&apos;deki kitapçılarda yan yana gör, stokta olanı tek
            bakışta bul. Koleksiyonunu tut, istek listeni oluştur, fiyat düşünce haberin olsun.
          </p>

          <SearchSection />

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
                <dd className="tabular font-display text-xl text-ink">{NUMBER.format(feed.stats.series)}</dd>
              </div>
              <div>
                <dt className="text-faint">Takip edilen mağaza</dt>
                <dd className="tabular font-display text-xl text-ink">{NUMBER.format(feed.stats.stores)}</dd>
              </div>
              <div>
                <dt className="text-faint">Güncel fiyat</dt>
                <dd className="tabular font-display text-xl text-ink">{NUMBER.format(feed.stats.offers)}</dd>
              </div>
            </dl>
          )}
        </div>

        {lead && (
          <div aria-hidden className="relative mx-auto hidden h-[25rem] w-full max-w-md lg:block">
            <div className="screentone absolute inset-6 rounded-[2rem] opacity-70 [mask-image:radial-gradient(closest-side,black,transparent)]" />
            {shelf[2] && (
              <Cover url={shelf[2].cover_url} alt="" className="absolute top-10 right-4 w-36 rotate-[7deg]" />
            )}
            {shelf[1] && (
              <Cover url={shelf[1].cover_url} alt="" className="absolute top-4 left-4 w-36 -rotate-[8deg]" />
            )}
            <Cover url={lead.cover_url} alt="" eager className="absolute top-12 left-1/2 w-44 -translate-x-1/2" />
            {lead.lowest_price !== null && (
              <div className="absolute bottom-6 left-1/2 w-64 -translate-x-1/2 rounded-xl border border-line bg-surface/95 p-3.5 shadow-lift backdrop-blur">
                <p className="truncate font-display text-base text-ink">{lead.title}</p>
                <div className="mt-1 flex items-baseline justify-between gap-3">
                  <span className="text-xs text-muted">
                    {lead.volume_count} cilt · {lead.in_stock_offers} stokta fiyat
                  </span>
                  <span className="tabular text-sm font-semibold text-ink">
                    {formatTL(lead.lowest_price)}
                    <span className="font-normal text-muted">&apos;den</span>
                  </span>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
