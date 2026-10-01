"use client";

/**
 * SearchBar: the home page's primary control — a large, paper-card search
 * field with the submit action inside it.
 */

export function SearchBar({
  value,
  onChange,
  onSubmit,
  loading,
  autoFocus = false,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  loading: boolean;
  autoFocus?: boolean;
}) {
  return (
    <form
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
      className="group flex w-full items-center gap-2 rounded-2xl border border-line-strong bg-surface p-1.5 shadow-card transition-shadow focus-within:border-ink/40 focus-within:shadow-lift"
    >
      <svg
        aria-hidden
        viewBox="0 0 24 24"
        className="ml-2.5 size-5 shrink-0 text-faint group-focus-within:text-ink"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      >
        <circle cx="11" cy="11" r="6.5" />
        <path d="m20 20-4.2-4.2" />
      </svg>
      <input
        type="search"
        name="q"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Seri ara: Berserk, Dragon Ball, Zom 100…"
        aria-label="Manga ara"
        autoComplete="off"
        autoFocus={autoFocus}
        className="min-w-0 flex-1 bg-transparent py-2.5 text-base text-ink placeholder:text-faint focus:outline-none sm:text-[1.05rem]"
      />
      <button
        type="submit"
        disabled={loading}
        className="inline-flex min-h-11 shrink-0 items-center rounded-xl bg-accent px-4 text-sm font-semibold text-on-accent transition-colors hover:bg-accent-hover disabled:cursor-wait disabled:opacity-70 sm:px-5 sm:text-base"
      >
        {loading ? "Aranıyor…" : "Manga ara"}
      </button>
    </form>
  );
}
