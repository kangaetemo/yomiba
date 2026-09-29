/**
 * Shared presentational primitives of the Yomiba design system.
 * Server-Component safe (no state, no effects).
 */

import Link from "next/link";
import type { ReactNode } from "react";

// -- Badge ----------------------------------------------------------------------------

export type BadgeTone = "deal" | "lowest" | "new" | "stock" | "soldout" | "stale" | "alert" | "wish" | "neutral";

const BADGE_TONES: Record<BadgeTone, string> = {
  // Deals and the lowest price read as the hanko seal: strong, not loud.
  deal: "bg-accent text-on-accent",
  lowest: "border border-accent/40 bg-accent-soft text-accent",
  new: "border border-new/25 bg-new-soft text-new",
  stock: "border border-ok/25 bg-ok-soft text-ok",
  soldout: "border border-bad/25 bg-bad-soft text-bad",
  stale: "border border-warn/25 bg-warn-soft text-warn",
  alert: "border border-accent/30 bg-surface text-accent",
  wish: "border border-new/30 bg-surface text-new",
  neutral: "border border-line bg-surface-2 text-ink-2",
};

export function Badge({
  tone = "neutral",
  children,
  className = "",
  dot = false,
}: {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
  /** A small leading status dot (stock states). */
  dot?: boolean;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[0.72rem] leading-5 font-semibold whitespace-nowrap ${BADGE_TONES[tone]} ${className}`}
    >
      {dot && <span aria-hidden className="size-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

// -- Section heading ------------------------------------------------------------------

/** Magazine-style section head: folio number + eyebrow, serif title, lead. */
export function SectionHeading({
  folio,
  eyebrow,
  title,
  lead,
  action,
  id,
}: {
  folio?: string;
  eyebrow?: string;
  title: string;
  lead?: ReactNode;
  action?: { href: string; label: string };
  id?: string;
}) {
  return (
    <header className="space-y-3">
      <div className="rule" aria-hidden />
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <div className="space-y-1">
          {(folio || eyebrow) && (
            <p className="eyebrow">
              {folio && <span className="tabular text-accent">No. {folio}</span>}
              {folio && eyebrow && <span aria-hidden> · </span>}
              {eyebrow}
            </p>
          )}
          <h2 id={id} className="text-2xl font-semibold text-ink sm:text-[1.9rem] sm:leading-tight">
            {title}
          </h2>
          {lead && <p className="max-w-2xl text-sm text-muted sm:text-base">{lead}</p>}
        </div>
        {action && (
          <Link
            href={action.href}
            className="group inline-flex min-h-11 items-center gap-1 text-sm font-semibold text-ink-2 hover:text-accent"
          >
            {action.label}
            <span aria-hidden className="transition-transform group-hover:translate-x-0.5">→</span>
          </Link>
        )}
      </div>
    </header>
  );
}

// -- Cover ----------------------------------------------------------------------------

/** A printed-book cover (2:3). Hot-linked from store / catalog CDNs, so a
 * plain <img>; next/image would need every store domain allow-listed. */
export function Cover({
  url,
  alt,
  className = "w-24",
  eager = false,
}: {
  url: string | null;
  alt: string;
  className?: string;
  eager?: boolean;
}) {
  if (!url) {
    return (
      <div
        aria-hidden
        className={`${className} cover-art screentone grid aspect-[2/3] shrink-0 place-items-center rounded-[5px] bg-surface-2`}
      >
        <span className="font-display text-2xl text-faint">読</span>
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={url}
      alt={alt}
      loading={eager ? "eager" : "lazy"}
      className={`${className} cover-art aspect-[2/3] shrink-0 rounded-[5px] bg-surface-2 object-cover`}
    />
  );
}

// -- Money ----------------------------------------------------------------------------

export function formatTL(price: number | null | undefined, digits: "auto" | 0 = "auto"): string {
  if (price === null || price === undefined || Number.isNaN(Number(price))) return "—";
  const value = Number(price);
  return new Intl.NumberFormat("tr-TR", {
    style: "currency",
    currency: "TRY",
    minimumFractionDigits: digits === 0 || Number.isInteger(value) ? 0 : 2,
    maximumFractionDigits: digits === 0 ? 0 : 2,
  }).format(value);
}

const DATE_FMT = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "long", year: "numeric" });
const DATE_SHORT = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "short", year: "numeric" });

/** "2023-06-22" -> "22 Haziran 2023" (date-only strings are local dates). */
export function formatDate(iso: string | null | undefined, short = false): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return (short ? DATE_SHORT : DATE_FMT).format(new Date(y, m - 1, d));
}

/** Volume label with the omnibus span: "Cilt 5 · 9–10". */
export function volumeTitle(
  number: number | null,
  coversFrom?: number | null,
  coversTo?: number | null,
): string {
  const base = number === null || number < 0 ? "Numarasız" : `Cilt ${number}`;
  return coversFrom && coversTo ? `${base} · ${coversFrom}–${coversTo}` : base;
}
