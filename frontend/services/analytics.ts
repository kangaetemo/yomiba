import { getJson } from "@/lib/api";

export type Totals = {
  visitors: number; returning_visitors: number; sessions: number; pageviews: number;
  pages_per_session: number; bounce_rate: number; avg_session_seconds: number;
  outbound: number; outbound_sessions: number; click_rate: number;
  searches: number; zero_result_searches: number; logged_in_sessions: number;
  new_users: number; wishlist_adds: number; price_alerts: number; collection_adds: number;
};
export type Point = { t: string | number; pageviews: number; visitors: number; outbound: number; searches: number };
export type Named = { name: string | null; sessions: number };
export type AnalyticsReport = {
  /** days: whole local days up to today; hours: rolling window up to now (one is null). */
  generated_at: string; days: number | null; hours: number | null; start: string; end: string;
  since: string; until: string; bucket: "hour" | "day";
  totals: Totals; previous: Totals; series: Point[];
  live: { sessions: number; pages: { path: string; sessions: number }[] };
  pages: { path: string; pageviews: number; visitors: number; avg_seconds: number }[];
  entry_pages: { path: string; sessions: number }[];
  exit_pages: { path: string; sessions: number }[];
  top_series: { series_id: number; title: string; path: string | null; pageviews: number; sessions: number; outbound: number }[];
  top_volumes: {
    volume_id: number; series: string; number: number | null; path: string | null;
    pageviews: number; sessions: number; outbound: number; click_rate: number | null;
  }[];
  stores: { store_id: number; name: string; clicks: number; sessions: number; volumes: number; trend: number[] }[];
  other_links: { host: string; clicks: number }[];
  searches: { query: string; count: number; avg_results: number | null; last: string }[];
  zero_searches: { query: string; count: number; last: string }[];
  search_click_rate: number | null;
  referrers: Named[]; utm_sources: Named[]; utm_campaigns: Named[];
  devices: Named[]; browsers: Named[]; systems: Named[]; countries: Named[];
  heatmap: number[][];
  funnel: { sessions: number; viewed_volume: number; clicked_store: number };
  session_depth: { pages: number; sessions: number }[];
  users_total: number;
  new_members: {
    id: number; name: string; email: string; created_at: string;
    method: "email" | "google" | "google+email"; admin: boolean; active: boolean;
    last_login: string | null; collection: number; wishlist: number; alerts: number;
  }[];
  retention_days: number;
};

/** key is the page's query string (/admin/analiz?gun=7, ?saat=24) and the API's. */
export const ANALYTICS_PERIODS = [
  { key: "gun=1", api: "days=1", label: "Bugün" },
  { key: "saat=24", api: "hours=24", label: "Son 24 saat" },
  { key: "gun=7", api: "days=7", label: "7 gün" },
  { key: "gun=30", api: "days=30", label: "30 gün" },
  { key: "gun=90", api: "days=90", label: "90 gün" },
  { key: "gun=365", api: "days=365", label: "1 yıl" },
] as const;
export type AnalyticsPeriod = (typeof ANALYTICS_PERIODS)[number];
export const DEFAULT_ANALYTICS_PERIOD = ANALYTICS_PERIODS.find((p) => p.key === "gun=30")!;

export const getAnalytics = (period: AnalyticsPeriod) => getJson<AnalyticsReport>(`/admin/analytics?${period.api}`);
