import type { Metadata } from "next";
import Link from "next/link";
import { Bricolage_Grotesque, Figtree } from "next/font/google";
import "./globals.css";
import { currentUserOrNull } from "@/services/auth";
import { LogoutButton } from "@/components/LogoutButton";

// Turkish needs latin-ext (ş, ğ, ı, İ).
const body = Figtree({
  variable: "--font-body",
  subsets: ["latin", "latin-ext"],
});

const display = Bricolage_Grotesque({
  variable: "--font-display-face",
  subsets: ["latin", "latin-ext"],
});

export const metadata: Metadata = {
  title: {
    default: "Yomiba — Manga fiyat karşılaştırma",
    template: "%s | Yomiba",
  },
  description:
    "Manga fiyatlarını Türk mağazaları (BKM Kitap, Gerekli Şeyler, Kitap Sepeti ve diğerleri) arasında karşılaştırın ve koleksiyonunuzu takip edin.",
};

/** Wordmark: "Yomiba" (読み場, "a place to read") with a hanko seal. */
function Logo() {
  return (
    <Link href="/" className="group flex items-center gap-2" aria-label="Yomiba ana sayfa">
      <span
        aria-hidden
        className="grid size-7 -rotate-3 place-items-center rounded-[5px] bg-accent text-[15px] leading-none font-bold text-on-accent shadow-[inset_0_0_0_1.5px_rgb(255_252_244/0.55)] transition-transform group-hover:rotate-0"
      >
        読
      </span>
      <span className="font-display text-xl font-extrabold tracking-tight text-ink">
        yomiba
      </span>
    </Link>
  );
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const user = await currentUserOrNull();
  const navLink = "text-ink-2 transition-colors hover:text-accent";
  return (
    <html lang="tr">
      <body className={`${body.variable} ${display.variable} flex min-h-dvh flex-col font-sans antialiased`}>
        <header className="sticky top-0 z-40 border-b border-line bg-paper/90 backdrop-blur">
          <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-4 py-3">
            <Logo />
            <nav className="flex items-center gap-4 text-sm">
              {user?.role === "ADMIN" && (
                <Link href="/admin" className={navLink}>
                  Admin
                </Link>
              )}
              {user ? (
                <>
                  <Link href="/collection" className={navLink}>
                    Koleksiyonum
                  </Link>
                  <span className="hidden text-muted sm:inline">{user.display_name}</span>
                  <LogoutButton />
                </>
              ) : (
                <>
                  <Link href="/login" className={navLink}>
                    Giriş yap
                  </Link>
                  <Link
                    href="/register"
                    className="rounded-lg bg-ink px-3 py-1.5 font-medium text-paper transition-colors hover:bg-accent"
                  >
                    Kayıt ol
                  </Link>
                </>
              )}
            </nav>
          </div>
        </header>

        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
          {children}
        </main>

        <footer className="screentone border-t border-line">
          <div className="bg-gradient-to-b from-paper to-paper/70">
            <p className="mx-auto max-w-5xl px-4 py-6 text-center text-xs text-muted">
              yomiba · Fiyatlar kamuya açık mağaza sayfalarından toplanır ve
              gecikmeli olabilir.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
