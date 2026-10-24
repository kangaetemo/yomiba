import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { InstagramStudio } from "@/components/admin/instagram/InstagramStudio";
import { LaunchStudio } from "@/components/admin/instagram/LaunchStudio";
import { Segmented } from "@/components/Segmented";
import { TIME_ZONE } from "@/lib/time";
import { currentUser } from "@/services/auth";
import { getInstagramLaunch, getInstagramReleases } from "@/services/instagram";

export const metadata: Metadata = { title: "Instagram taslakları" };

const KINDS = [
  { key: "hafta", label: "Haftanın çıkanları", href: "/admin/instagram" },
  { key: "acilis", label: "Site açılışı", href: "/admin/instagram?tur=acilis" },
];

const WEEKS = [
  { key: "-2", label: "2 hafta önce" },
  { key: "-1", label: "Geçen hafta" },
  { key: "0", label: "Bu hafta" },
  { key: "1", label: "Gelecek hafta" },
];

const DAY_MONTH = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "long", timeZone: "UTC" });
const DAY = new Intl.DateTimeFormat("tr-TR", { day: "numeric", timeZone: "UTC" });
const iso = (d: Date) => d.toISOString().slice(0, 10);

/** Monday..Sunday of the Turkish week `offset` weeks from this one. */
function week(offset: number): { start: Date; end: Date } {
  const parts = new Intl.DateTimeFormat("en", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: TIME_ZONE })
    .formatToParts(new Date());
  const get = (type: string) => Number(parts.find((p) => p.type === type)!.value);
  const today = new Date(Date.UTC(get("year"), get("month") - 1, get("day")));
  const start = new Date(today);
  start.setUTCDate(today.getUTCDate() - ((today.getUTCDay() + 6) % 7) + offset * 7);
  const end = new Date(start);
  end.setUTCDate(start.getUTCDate() + 6);
  return { start, end };
}

/** "20–26 Ekim", "27 Ekim – 2 Kasım". */
function weekLabel(start: Date, end: Date): string {
  return start.getUTCMonth() === end.getUTCMonth()
    ? `${DAY.format(start)}–${DAY_MONTH.format(end)}`
    : `${DAY_MONTH.format(start)} – ${DAY_MONTH.format(end)}`;
}

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);

export default async function InstagramPage({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const user = await currentUser();
  if (!user) redirect("/login?next=%2Fadmin%2Finstagram");
  if (user.role !== "ADMIN") redirect("/");
  const query = await searchParams;
  const launch = one(query.tur) === "acilis";
  const header = (
    <header className="space-y-1">
      <p className="text-sm"><Link href="/admin" className="text-new hover:underline">← Admin</Link></p>
      <h1 className="text-2xl font-bold tracking-tight text-ink">Instagram taslakları</h1>
      <p className="text-sm text-muted">
        {launch
          ? "Sitenin açıldığını duyuran kaydırmalı post: katalogdaki gerçek sayılar ve mağazalar arasında fiyatı en çok değişen ciltlerden biriyle."
          : "Haftanın çıkan ciltlerinden kaydırmalı post: sitedeki kapaklar ve şu anki mağaza fiyatlarıyla."}
        {" "}Görselleri indirip açıklama metnini kopyalayarak Instagram&apos;da paylaşabilirsin; buradan hiçbir şey otomatik paylaşılmaz.
      </p>
    </header>
  );
  const kinds = (
    <Segmented label="Post türü" current="page" items={KINDS.map((k) => ({
      key: k.key, href: k.href, active: (k.key === "acilis") === launch, children: k.label,
    }))} />
  );
  if (launch) {
    const data = await getInstagramLaunch().catch(() => null);
    return (
      <div className="space-y-6">
        {header}
        {kinds}
        {data ? <LaunchStudio data={data} /> : (
          <p className="rounded-xl border border-line bg-surface p-5 text-sm text-muted">Veriler yüklenemedi. Sayfayı yenilemeyi dene.</p>
        )}
      </div>
    );
  }

  const offset = WEEKS.find((w) => w.key === one(query.hafta))?.key ?? "0";
  const { start, end } = week(Number(offset));
  const label = weekLabel(start, end);
  const data = await getInstagramReleases(iso(start), iso(end)).catch(() => null);

  return (
    <div className="space-y-6">
      {header}
      {kinds}
      <Segmented label="Hafta" current="page" items={WEEKS.map((w) => ({
        key: w.key, href: w.key === "0" ? "/admin/instagram" : `/admin/instagram?hafta=${w.key}`,
        active: w.key === offset, children: w.label,
      }))} />
      <h2 className="font-semibold text-ink">
        Bu hafta çıkanlar · {label}
        {data ? <span className="ml-2 font-normal text-muted">{data.volumes.length} cilt</span> : null}
      </h2>
      {data ? (
        <InstagramStudio key={data.start} volumes={data.volumes} weekLabel={label} fileStem={`yomiba-cikanlar-${data.start}`} />
      ) : (
        <p className="rounded-xl border border-line bg-surface p-5 text-sm text-muted">Veriler yüklenemedi. Sayfayı yenilemeyi dene.</p>
      )}
    </div>
  );
}
