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
        className="min-w-0 flex-1 rounded-xl border border-neutral-700 bg-neutral-900 px-4 py-3 text-base text-neutral-100 placeholder:text-neutral-500 focus:border-orange-500 focus:outline-none focus:ring-2 focus:ring-orange-500/30"
      />
      <button
        type="submit"
        disabled={loading}
        className="shrink-0 rounded-xl bg-orange-500 px-5 py-3 text-base font-semibold text-neutral-950 transition-colors hover:bg-orange-400 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {loading ? "Aranıyor…" : "Ara"}
      </button>
    </form>
  );
}
