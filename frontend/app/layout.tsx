import type { Metadata } from "next";
import Link from "next/link";
import { Figtree, Fraunces } from "next/font/google";
import "./globals.css";
import { currentUserOrNull } from "@/services/auth";
import { AccountMenu } from "@/components/AccountMenu";
import { SearchDialogButton } from "@/components/SearchDialog";
import { THEME_SCRIPT, ThemeToggle } from "@/components/ThemeToggle";
import { LoginLink } from "@/components/LoginLink";
import { SiteTracker } from "@/components/SiteTracker";
import { DEFAULT_OG_IMAGE, SITE_NAME, SITE_URL } from "@/lib/site";

// Turkish needs latin-ext (ş, ğ, ı, İ).
const body = Figtree({
  variable: "--font-body",
  subsets: ["latin", "latin-ext"],
});

// Editorial display serif: warm, soft-edged, with optical sizes.
const display = Fraunces({
  variable: "--font-display-face",
  subsets: ["latin", "latin-ext"],
  axes: ["opsz", "SOFT"],
});

export const metadata: Metadata = {
  // Relative canonical / Open Graph URLs (and cover paths) resolve against it.
  metadataBase: new URL(SITE_URL),
  applicationName: SITE_NAME,
  title: {
    default: "Yomiba - Manga fiyat karşılaştırma ve koleksiyon takibi",
    template: "%s | Yomiba",
  },
  description:
    "Manga fiyatlarını Türk kitapçıları (BKM Kitap, Gerekli Şeyler, Kitap Sepeti ve diğerleri) arasında karşılaştır, koleksiyonunu takip et, fiyat alarmı kur.",
  openGraph: { type: "website", siteName: SITE_NAME, locale: "tr_TR", images: [DEFAULT_OG_IMAGE] },
  twitter: { card: "summary" },
};

/** Wordmark: "Yomiba" (読み場, "a place to read") with a hanko seal. */
function Logo() {
  return (
    <Link href="/" className="group flex min-h-11 items-center gap-2.5" aria-label="Yomiba ana sayfa">
      <span
        aria-hidden
        className="grid size-8 -rotate-3 place-items-center rounded-[6px] bg-accent font-display text-[17px] leading-none font-bold text-on-accent shadow-[inset_0_0_0_1.5px_rgb(255_253_248/0.5)] transition-transform duration-300 group-hover:rotate-0"
      >
        読
      </span>
      {/* Under 360px the seal alone carries the brand, so the header fits. */}
      <span className="font-display text-[1.45rem] leading-none font-semibold tracking-tight text-ink max-[359px]:sr-only">
        yomiba
      </span>
    </Link>
  );
}

const SECTIONS = [
  { href: "/#indirimler", label: "İndirimler" },
  { href: "/#yeni", label: "Yeni çıkanlar" },
  { href: "/#populer", label: "Popüler" },
];

/** Crawlable links to every list page, on every page. */
const FOOTER_LINKS = [
  { href: "/seriler", label: "Tüm seriler" },
  { href: "/one-shot", label: "One shot" },
  { href: "/takvim", label: "Yayın takvimi" },
  { href: "/indirimler", label: "İndirimler" },
];

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const user = await currentUserOrNull();
  const navLink = "rounded-md px-1 py-2 text-ink-2 transition-colors hover:text-accent";
  return (
    // data-theme is set before paint by THEME_SCRIPT, so it differs from the
    // server render by design.
    <html lang="tr" className="scroll-smooth" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className={`${body.variable} ${display.variable} flex min-h-dvh flex-col font-sans text-[1rem] antialiased`}>
        <a
          href="#icerik"
          className="sr-only z-50 rounded-lg bg-ink px-3 py-2 text-paper focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
        >
          İçeriğe geç
        </a>
        <header className="sticky top-0 z-40 border-b border-line bg-paper md:bg-paper/85 md:backdrop-blur-md">
          <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
            <Logo />
            <nav aria-label="Bölümler" className="hidden items-center gap-5 text-sm md:flex">
              <SearchDialogButton className={`${navLink} inline-flex items-center gap-1.5`} />
              {SECTIONS.map((s) => (
                <Link key={s.href} href={s.href} className={navLink}>
                  {s.label}
                </Link>
              ))}
              <Link href="/seriler" className={navLink}>
                Tüm seriler
              </Link>
            </nav>
            <nav aria-label="Hesap" className="flex items-center gap-1.5 text-sm sm:gap-3">
              <ThemeToggle />
              {user?.role === "ADMIN" && (
                <Link href="/admin" className={`${navLink} hidden lg:inline`}>
                  Admin
                </Link>
              )}
              {user ? (
                <>
                  <Link
                    href="/collection"
                    className="hidden min-h-11 items-center rounded-lg border border-line bg-surface px-3 font-semibold text-ink transition-colors hover:border-line-strong sm:inline-flex"
                  >
                    Koleksiyonum
                  </Link>
                  {/* Account settings, admin and logout live in this menu. */}
                  <AccountMenu name={user.display_name} admin={user.role === "ADMIN"} />
                </>
              ) : (
                <>
                  <LoginLink className={`${navLink} min-h-11 inline-flex items-center`}>
                    Giriş yap
                  </LoginLink>
                  <LoginLink
                    to="/register"
                    className="inline-flex min-h-11 items-center rounded-lg bg-ink px-3.5 font-semibold text-paper transition-colors hover:bg-accent"
                  >
                    Kayıt ol
                  </LoginLink>
                </>
              )}
            </nav>
          </div>
          {/* Small screens: the section links get their own quiet row. */}
          <nav aria-label="Bölümler" className="border-t border-line md:hidden">
            <ul className="mx-auto flex max-w-6xl justify-between px-4 text-[0.95rem]">
              <li>
                <SearchDialogButton className="inline-flex min-h-11 items-center gap-1.5 px-1 text-ink-2 hover:text-accent" />
              </li>
              {SECTIONS.map((s) => (
                <li key={s.href}>
                  <Link href={s.href} className="inline-flex min-h-11 items-center px-1 text-ink-2 hover:text-accent">
                    {s.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </header>

        <main id="icerik" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
          {children}
        </main>

        <footer className="mt-12 border-t border-line bg-surface/60">
          <div className="mx-auto max-w-6xl space-y-3 px-4 py-10 sm:px-6">
            <Logo />
            <p className="max-w-sm text-sm text-muted">
              Türkiye&apos;deki manga baskılarının fiyatını mağazalar arasında karşılaştırır,
              koleksiyonunu ve istek listeni tek yerde tutar.
            </p>
            <nav aria-label="Site" className="pt-2">
              <ul className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
                {FOOTER_LINKS.map((l) => (
                  <li key={l.href}>
                    <Link href={l.href} className="inline-flex min-h-9 items-center text-ink-2 hover:text-accent">
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
            <p className="text-xs text-faint">
              Fiyatlar mağazaların kamuya açık sayfalarından toplanır ve gecikmeli olabilir.
            </p>
          </div>
        </footer>
        <SiteTracker />
      </body>
    </html>
  );
}
