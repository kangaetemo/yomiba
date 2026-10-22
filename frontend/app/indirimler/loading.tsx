import { ResultsSkeleton } from "@/components/LoadingSkeleton";

export default function DealsLoading() {
  return (
    <div className="space-y-8" aria-busy="true" aria-label="İndirimler yükleniyor">
      <div className="max-w-2xl animate-pulse space-y-3">
        <div className="h-3 w-24 rounded bg-surface-2" />
        <div className="h-10 w-2/3 rounded bg-surface-2" />
      </div>
      <ResultsSkeleton count={6} />
    </div>
  );
}
