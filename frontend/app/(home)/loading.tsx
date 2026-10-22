import { LineSkeleton, ShelfSkeleton } from "@/components/LoadingSkeleton";

/** Shown at once when the logo or a home link is clicked, while the server
 * renders the page. Only the home page (this route group) streams: elsewhere
 * a missing series must still answer with a real 404. */
export default function HomeLoading() {
  return (
    <div className="space-y-16 sm:space-y-20" aria-busy="true" aria-label="Ana sayfa yükleniyor">
      <div className="max-w-xl animate-pulse space-y-6">
        <div className="h-12 w-full rounded-lg bg-surface-2 sm:h-16" />
        <LineSkeleton lines={2} />
      </div>
      <ShelfSkeleton />
    </div>
  );
}
