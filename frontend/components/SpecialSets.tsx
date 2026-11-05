/** SpecialSets: box sets and bundles that include this series, sold as one
 * product (Komik Şeyler's JoJo Part 1 + Part 2 Kutulu Set). Added by an
 * admin; price and stock follow the store page. Server-Component safe. */

import Link from "next/link";
import { Badge, formatTL } from "@/components/ui";
import { storeLink } from "@/lib/storeLink";
import { seriesPath } from "@/lib/paths";
import { formatDateTime } from "@/lib/time";
import type { SpecialSet } from "@/types";

export function SpecialSets({ sets }: { sets: SpecialSet[] }) {
  if (sets.length === 0) return null;
  return (
    <section aria-labelledby="ozel-setler" className="space-y-3">
      <h2 id="ozel-setler" className="eyebrow">
        Özel set
      </h2>
      <ul className="grid gap-3 lg:grid-cols-2">
        {sets.map((s) => (
          <li key={s.id}>
            <SetCard set={s} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function SetCard({ set: s }: { set: SpecialSet }) {
  const buyable = s.in_stock !== false && s.price !== null;
  return (
    <div className="flex gap-4 rounded-xl border border-line bg-surface p-4 shadow-card">
      {s.image_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={s.image_url} alt="" className="h-28 w-24 shrink-0 rounded-md bg-surface-2 object-contain" loading="lazy" />
      ) : null}
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          {s.preorder ? <Badge tone="new">Ön sipariş</Badge> : null}
          {s.in_stock === false ? (
            <Badge tone="soldout" dot>Stokta yok</Badge>
          ) : !s.preorder ? (
            <Badge tone="stock" dot>Stokta</Badge>
          ) : null}
        </div>
        <p className="font-semibold leading-snug text-ink">{s.title}</p>
        <p className="text-sm text-muted">
          {s.store}
          {s.also.length > 0 ? (
            <>
              {" · içinde: "}
              {s.also.map((a, i) => (
                <span key={a.slug}>
                  {i > 0 ? ", " : ""}
                  <Link href={seriesPath(a.slug)} className="underline decoration-line-strong underline-offset-4 hover:text-ink">
                    {a.title}
                  </Link>
                </span>
              ))}
            </>
          ) : null}
        </p>
        <div className="mt-auto flex flex-wrap items-center justify-between gap-3">
          <div>
            <span className={`tabular text-xl font-semibold ${buyable ? "text-ink" : "text-muted"}`}>{formatTL(s.price)}</span>
            {s.last_checked ? <span className="block text-xs text-faint">kontrol: {formatDateTime(s.last_checked)}</span> : null}
          </div>
          <a
            href={storeLink(s.product_url)}
            target="_blank"
            // No `noreferrer`: the store should see the visit came from Yomiba.
            rel="noopener"
            className={`inline-flex min-h-11 items-center gap-1.5 rounded-lg px-3.5 text-sm font-semibold transition-colors ${
              buyable ? "bg-ink text-paper hover:bg-accent" : "text-muted underline decoration-line-strong underline-offset-4 hover:text-ink"
            }`}
          >
            {buyable ? "Mağazaya git" : "Mağazada gör"}
            <span aria-hidden>↗</span>
            <span className="sr-only">({s.store}, yeni sekmede açılır)</span>
          </a>
        </div>
      </div>
    </div>
  );
}
