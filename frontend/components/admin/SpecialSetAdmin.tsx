"use client";

/** Admin: add box sets by store product URL, link them to series, and
 * manage the list (refresh, pre-order flag, hide, delete). */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Badge, formatTL } from "@/components/ui";
import { seriesPath } from "@/lib/paths";
import { formatDateTime } from "@/lib/time";
import {
  createSpecialSet, deleteSpecialSet, refreshSpecialSet, updateSpecialSet,
  type AdminSpecialSet, type SeriesOption,
} from "@/services/specialSets";

const fold = (s: string) => s.toLocaleLowerCase("tr-TR").normalize("NFD").replace(/[̀-ͯ]/g, "");

function SeriesPicker({ series, selected, onChange }: {
  series: SeriesOption[]; selected: number[]; onChange: (ids: number[]) => void;
}) {
  const [q, setQ] = useState("");
  const matches = useMemo(() => {
    const key = fold(q.trim());
    if (key.length < 2) return [];
    return series.filter((s) => fold(s.title).includes(key) && !selected.includes(s.id)).slice(0, 8);
  }, [q, series, selected]);
  const byId = useMemo(() => new Map(series.map((s) => [s.id, s])), [series]);
  return <div className="space-y-2">
    <div className="flex flex-wrap gap-2">
      {selected.map((id) => <button key={id} type="button" onClick={() => onChange(selected.filter((x) => x !== id))}
        className="rounded-full border border-line-strong px-3 py-1 text-sm text-ink hover:bg-surface-2">
        {byId.get(id)?.title ?? id} <span aria-hidden>×</span><span className="sr-only">kaldır</span>
      </button>)}
    </div>
    <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Seri ara (ör. jojo)"
      className="w-full rounded-lg border border-line bg-paper px-3 py-2 text-sm" />
    {matches.length > 0 && <ul className="divide-y divide-line rounded-lg border border-line">
      {matches.map((s) => <li key={s.id}>
        <button type="button" onClick={() => { onChange([...selected, s.id]); setQ(""); }}
          className="block w-full px-3 py-2 text-left text-sm text-ink hover:bg-surface-2">{s.title}</button>
      </li>)}
    </ul>}
  </div>;
}

export function SpecialSetAdmin({ sets, series }: { sets: AdminSpecialSet[]; series: SeriesOption[] }) {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [preorder, setPreorder] = useState(false);
  const [ids, setIds] = useState<number[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    try {
      await createSpecialSet({ product_url: url.trim(), series_ids: ids, title: title.trim() || undefined, preorder });
      setUrl(""); setTitle(""); setPreorder(false); setIds([]);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Eklenemedi");
    } finally {
      setPending(false);
    }
  }

  return <div className="space-y-6">
    <form onSubmit={add} className="space-y-4 rounded-xl border border-line bg-surface p-5">
      <h2 className="font-semibold text-ink">Yeni set ekle</h2>
      <label className="block space-y-1 text-sm">
        <span className="text-muted">Ürün linki</span>
        <input required value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://komikseyler.com.tr/urun/..."
          className="w-full rounded-lg border border-line bg-paper px-3 py-2" />
      </label>
      <div className="space-y-1 text-sm">
        <span className="text-muted">Hangi serilerin sayfasında görünsün?</span>
        <SeriesPicker series={series} selected={ids} onChange={setIds} />
      </div>
      <label className="block space-y-1 text-sm">
        <span className="text-muted">Başlık (boş bırakırsan mağazadaki ürün adı kullanılır)</span>
        <input value={title} onChange={(e) => setTitle(e.target.value)} className="w-full rounded-lg border border-line bg-paper px-3 py-2" />
      </label>
      <label className="flex items-center gap-2 text-sm text-ink">
        <input type="checkbox" checked={preorder} onChange={(e) => setPreorder(e.target.checked)} /> Ön sipariş
      </label>
      {error && <p className="text-sm text-accent">{error}</p>}
      <button disabled={pending || !url.trim() || ids.length === 0}
        className="min-h-11 rounded-lg bg-ink px-4 text-sm font-semibold text-paper hover:bg-accent disabled:opacity-50">
        {pending ? "Ekleniyor…" : "Ekle"}
      </button>
    </form>

    {sets.length === 0 ? (
      <p className="rounded-xl border border-dashed border-line-strong bg-surface/70 p-8 text-center text-sm text-muted">Henüz özel set yok.</p>
    ) : (
      <ul className="space-y-3">{sets.map((s) => <SetRow key={s.id} set={s} />)}</ul>
    )}
  </div>;
}

function SetRow({ set: s }: { set: AdminSpecialSet }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    setPending(true);
    setError(null);
    try {
      await action();
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Olmadı");
    } finally {
      setPending(false);
    }
  }

  const button = "min-h-9 rounded-lg border border-line px-3 text-sm text-ink hover:bg-surface-2 disabled:opacity-50";
  return <li className={`flex gap-4 rounded-xl border border-line bg-surface p-4 ${s.active ? "" : "opacity-60"}`}>
    {s.image_url ? (
      // eslint-disable-next-line @next/next/no-img-element
      <img src={s.image_url} alt="" className="h-20 w-16 shrink-0 rounded object-contain" />
    ) : null}
    <div className="min-w-0 flex-1 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {!s.active && <Badge tone="neutral">Gizli</Badge>}
        {s.preorder && <Badge tone="new">Ön sipariş</Badge>}
        {s.in_stock === false ? <Badge tone="soldout" dot>Stokta yok</Badge> : s.in_stock ? <Badge tone="stock" dot>Stokta</Badge> : null}
        <span className="tabular font-semibold text-ink">{formatTL(s.price)}</span>
        <span className="text-sm text-muted">{s.store}</span>
      </div>
      <a href={s.product_url} target="_blank" rel="noopener" className="block font-semibold text-ink hover:text-accent">{s.title} ↗</a>
      <p className="text-sm text-muted">
        {s.series.map((x, i) => <span key={x.id}>{i > 0 ? ", " : ""}{x.slug ? <Link href={seriesPath(x.slug)} className="underline underline-offset-4">{x.title}</Link> : x.title}</span>)}
      </p>
      <p className="text-xs text-faint">
        {s.last_checked ? `kontrol: ${formatDateTime(s.last_checked)}` : "henüz okunamadı"}
        {s.check_error ? ` · hata: ${s.check_error}` : ""}
      </p>
      {s.price === null && s.active && <p className="text-xs text-accent">Fiyat okunamadığı için seri sayfasında görünmüyor.</p>}
      {error && <p className="text-sm text-accent">{error}</p>}
      <div className="flex flex-wrap gap-2">
        <button className={button} disabled={pending} onClick={() => run(() => refreshSpecialSet(s.id))}>Şimdi güncelle</button>
        <button className={button} disabled={pending} onClick={() => run(() => updateSpecialSet(s.id, { preorder: !s.preorder }))}>
          {s.preorder ? "Ön sipariş değil" : "Ön sipariş"}
        </button>
        <button className={button} disabled={pending} onClick={() => run(() => updateSpecialSet(s.id, { active: !s.active }))}>
          {s.active ? "Gizle" : "Göster"}
        </button>
        <button className={button} disabled={pending} onClick={() => {
          if (window.confirm("Bu set silinsin mi?")) void run(() => deleteSpecialSet(s.id));
        }}>Sil</button>
      </div>
    </div>
  </li>;
}
