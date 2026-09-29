"use client";

/**
 * SearchBar: controlled input + submit button for the home page search.
 */

export function SearchBar({
  value,
  onChange,
  onSubmit,
  loading,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  loading: boolean;
}) {
  return (
    <form
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
      className="flex w-full gap-2"
    >
      <input
        type="search"
        name="q"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Manga ara… (örn. Berserk, One Piece)"
        aria-label="Manga ara"
        className="min-w-0 flex-1 rounded-xl border border-line-strong bg-surface px-4 py-3 text-base text-ink placeholder:text-faint focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
      />
      <button
        type="submit"
        disabled={loading}
        className="shrink-0 rounded-xl bg-accent px-5 py-3 text-base font-semibold text-on-accent transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-60"
      >
        {loading ? "Aranıyor…" : "Ara"}
      </button>
    </form>
  );
}
