import Link from "next/link";
import { getJson } from "@/lib/api";
import { volumeLabel } from "@/lib/volumeLabel";

/**
 * DropsSection (server component): "Son indirimler" strip on the home page.
 *
 * Data = price drops the app actually observed (price_history), fetched
 * server-side from GET /price-drops. If the backend is unreachable the whole
 * section is hidden — the home page must never break because of the feed.
 */

interface Drop {
  listing_id: number;
  volume_id: number;
  series_id: number;
  series_title: string;
  volume_number: number | null; // 0 is a real volume; negative = unresolved.
  store_name: string;
  old_price: number | null;
  new_price: number | null;
  drop_pct: number;
  changed_at: string;
  in_stock: boolean;
  product_url: string;
  image_url: string | null;
}

function fmtPrice(v: number): string {
  return Number.isInteger(v) ? String(v) : v.toFixed(2);
}

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const m = Math.max(0, Math.round(ms / 60000));
  if (m < 1) return "az önce";
  if (m < 60) return `${m} dk önce`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} sa önce`;
  return `${Math.round(h / 24)} gün önce`;
}

export async function DropsSection() {
  let drops: Drop[] = [];
  try {
    const data = await getJson<{ drops: Drop[] }>("/price-drops?hours=24&limit=12");
    drops = data.drops;
  } catch {
    return null; // Backend down: silently hide the strip.
  }

  if (drops.length === 0) {
    return (
      <section className="rounded-xl border border-neutral-800 bg-neutral-900/50 p-4">
        <h2 className="text-sm font-semibold text-neutral-300">
          🔥 Son indirimler
        </h2>
        <p className="mt-1.5 text-sm text-neutral-500">
          Son 24 saatte gözlenen fiyat düşüşü yok. Fiyatlar düzenli olarak
          (varsayılan 12 saatte bir) otomatik kontrol edilir; düşüş olursa
          burada görünecek.
        </p>
      </section>
    );
  }

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold text-neutral-50">
          🔥 Son indirimler
        </h2>
        <span className="text-xs text-neutral-500">
          son 24 saatte gözlenen fiyat düşüşleri
        </span>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {drops.map((d) => (
          <Link
            key={d.listing_id}
            href={`/volume/${d.volume_id}`}
            className={`flex gap-3 rounded-xl border border-neutral-800 bg-neutral-900/70 p-3 transition-colors hover:border-orange-500/50 ${
              d.in_stock ? "" : "opacity-60"
            }`}
          >
            {d.image_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={d.image_url}
                alt=""
                className="h-20 w-14 shrink-0 rounded-md object-cover"
              />
            ) : (
              <div className="flex h-20 w-14 shrink-0 items-center justify-center rounded-md bg-neutral-800 text-xl">
                📖
              </div>
            )}
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-neutral-100">
                {d.series_title}
                <span className="text-neutral-400"> · {volumeLabel(d.volume_number)}</span>
              </p>
              <p className="mt-0.5 truncate text-xs text-neutral-500">
                {d.store_name} · {timeAgo(d.changed_at)}
                {!d.in_stock && " · stokta yok"}
              </p>
              <p className="mt-2 flex items-baseline gap-2">
                {d.old_price !== null && (
                  <s className="text-xs text-neutral-500">₺{fmtPrice(d.old_price)}</s>
                )}
                <span className="text-base font-semibold text-neutral-50">
                  ₺{d.new_price !== null ? fmtPrice(d.new_price) : "—"}
                </span>
                <span className="rounded-full bg-orange-500/15 px-2 py-0.5 text-xs font-semibold text-orange-400">
                  %{d.drop_pct} indirim
                </span>
              </p>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
