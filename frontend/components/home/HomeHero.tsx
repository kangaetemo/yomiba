/**
 * HomeHero: headline, the search (the page's main job), CTAs and a real
 * "shelf" of catalog covers with their actual lowest prices on the right.
 * Nothing on this shelf is illustrative: covers and prices come from /home.
 */

import Link from "next/link";
import { cookies } from "next/headers";
import { SearchSection } from "@/components/SearchSection";
import { HeroShelf } from "@/components/home/HeroShelf";
import { HERO_HISTORY_COOKIE, parseHeroHistory, pickHeroSeries } from "@/lib/heroSelection";
import type { HomeFeed } from "@/types";


export async function HomeHero({ feed, signedIn }: { feed: HomeFeed | null; signedIn: boolean }) {
  const recent = parseHeroHistory((await cookies()).get(HERO_HISTORY_COOKIE)?.value);
  const shelf = pickHeroSeries(
    feed?.hero_series ?? feed?.popular_series ?? [],
    recent,
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
            Aynı cilt,{" "}
            <em className="font-sans font-bold tracking-tight text-accent not-italic">
              en uygun fiyat
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

        </div>

        {lead && <HeroShelf key={shelf.map((s) => s.id).join("-")} series={shelf} />}
      </div>
    </section>
  );
}

