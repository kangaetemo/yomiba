import { HomeHero } from "@/components/home/HomeHero";
import { HotDeals } from "@/components/home/HotDeals";
import { HowItWorks } from "@/components/home/HowItWorks";
import { NewVolumes } from "@/components/home/NewVolumes";
import { PopularSeries } from "@/components/home/PopularSeries";
import { currentUserOrNull } from "@/services/auth";
import { getHomeFeed, getPriceDrops } from "@/services/catalog";
import type { HomeFeed, PriceDrop } from "@/types";

export const dynamic = "force-dynamic";

const DEAL_WINDOW_DAYS = 7;

export default async function HomePage() {
  // Each feed degrades on its own: a failing shelf is hidden, the page and
  // the search always render.
  const [feed, drops, user] = await Promise.all([
    getHomeFeed().catch((): HomeFeed | null => null),
    getPriceDrops(DEAL_WINDOW_DAYS * 24, 7)
      .then((d) => d.drops)
      .catch((): PriceDrop[] | null => null),
    currentUserOrNull(),
  ]);

  return (
    <div className="space-y-16 sm:space-y-20">
      <HomeHero feed={feed} signedIn={Boolean(user)} />
      {feed && <PopularSeries series={feed.popular_series} oneShots={feed.one_shots ?? []} />}
      <HotDeals drops={drops} windowDays={DEAL_WINDOW_DAYS} />
      {feed && <NewVolumes volumes={feed.new_volumes} />}
      <HowItWorks signedIn={Boolean(user)} />
    </div>
  );
}
