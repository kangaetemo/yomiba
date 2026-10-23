/** Blurb: a volume's back-cover text (or a series' first volume's, as its
 * story intro), read from a store's product page. */

export function Blurb({ id, title, text, source }: { id: string; title: string; text?: string | null; source?: string | null }) {
  if (!text) return null;
  return (
    <section aria-labelledby={id} className="max-w-3xl space-y-2">
      <h2 id={id} className="eyebrow">
        {title}
      </h2>
      <div className="space-y-2 text-sm leading-relaxed text-ink-2 sm:text-base">
        {text.split("\n").map((paragraph, i) => (
          <p key={i}>{paragraph}</p>
        ))}
      </div>
      {source && <p className="text-xs text-faint">Tanıtım yazısı: {source}</p>}
    </section>
  );
}
