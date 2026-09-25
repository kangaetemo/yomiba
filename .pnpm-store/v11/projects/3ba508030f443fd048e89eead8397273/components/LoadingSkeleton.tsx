/**
 * LoadingSkeleton: pulsing placeholder blocks for loading states.
 */

export function CardSkeleton() {
  return (
    <div className="animate-pulse rounded-xl border border-neutral-800 bg-neutral-900 p-4">
      <div className="flex gap-4">
        <div className="h-28 w-20 shrink-0 rounded-lg bg-neutral-800" />
        <div className="flex-1 space-y-3 py-1">
          <div className="h-4 w-3/4 rounded bg-neutral-800" />
          <div className="h-3 w-1/2 rounded bg-neutral-800" />
          <div className="h-3 w-1/3 rounded bg-neutral-800" />
        </div>
      </div>
    </div>
  );
}

export function ResultsSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {Array.from({ length: count }).map((_, i) => (
        <CardSkeleton key={i} />
      ))}
    </div>
  );
}

export function LineSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="animate-pulse space-y-3">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="h-5 w-full rounded bg-neutral-800" />
      ))}
    </div>
  );
}
