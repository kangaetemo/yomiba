import type { Metadata } from "next";
import { openGraph } from "@/lib/site";
import { HomeHero } from "@/components/home/HomeHero";
import { HotDeals } from "@/components/home/HotDeals";
import { HowItWorks } from "@/components/home/HowItWorks";
import { NewSeries } from "@/components/home/NewSeries";
import { NewVolumes } from "@/components/home/NewVolumes";
import { OneShots, PopularSeries } from "@/components/home/PopularSeries";
import { currentUserOrNull } from "@/services/auth";
import { getHomeFeed, getPriceDrops } from "@/services/catalog";
import type { HomeFeed, PriceDrop } from "@/types";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  alternates: { canonical: "/" },
  openGraph: openGraph({
    title: "Yomiba - Manga fiyat karşılaştırma ve koleksiyon takibi",
    description: "Manga fiyatlarını Türk kitapçıları arasında karşılaştır, koleksiyonunu takip et, fiyat alarmı kur.",
    url: "/",
  }),
};

const DEAL_WINDOW_DAYS = 7;
/** The feed carries a wider pool for the hero; the shelf shows the top of it. */
const SHELF_SIZE = 8;

export default async function HomePage() {
  // Each feed degrades on its own: a failing shelf is hidden, the page and
  // the search always render.
  const [feed, drops, user] = await Promise.all([
    getHomeFeed().catch((): HomeFeed | null => null),
    getPriceDrops(DEAL_WINDOW_DAYS * 24, 6, { significant: true, sort: "percent" })
      .then((d) => d.drops)
      .catch((): PriceDrop[] | null => null),
    currentUserOrNull(),
  ]);

  return (
    <div className="space-y-16 sm:space-y-20">
      <HomeHero feed={feed} signedIn={Boolean(user)} />
      {feed && <PopularSeries series={feed.popular_series.slice(0, SHELF_SIZE)} />}
      <HotDeals drops={drops} windowDays={DEAL_WINDOW_DAYS} />
      {feed && <NewVolumes volumes={feed.new_volumes} />}
      {feed && <NewSeries series={feed.new_series ?? []} />}
      {feed && <OneShots series={feed.one_shots ?? []} />}
      <HowItWorks signedIn={Boolean(user)} />
    </div>
  );
}
