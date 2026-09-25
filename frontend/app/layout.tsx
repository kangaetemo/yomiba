import type { Metadata } from "next";
import Link from "next/link";
import { Geist } from "next/font/google";
import "./globals.css";
import { currentUser } from "@/services/auth";
import { LogoutButton } from "@/components/LogoutButton";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "Yomiba — Manga fiyat karşılaştırma",
    template: "%s | Yomiba",
  },
  description:
    "Manga fiyatlarını Türk mağazaları (Amazon, BKM Kitap, D&R ve diğerleri) arasında karşılaştırın ve koleksiyonunuzu takip edin.",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const user = await currentUser();
  return (
    <html lang="tr">
      <body className={`${geistSans.variable} font-sans antialiased`}>
        <header className="sticky top-0 z-40 border-b border-neutral-800 bg-neutral-950/90 backdrop-blur">
          <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-4 py-3">
            <Link
              href="/"
              className="text-xl font-bold tracking-tight text-neutral-50"
            >
              Yom<span className="text-orange-500">iba</span>
            </Link>
            <span className="text-xs text-neutral-500">
              {user?.role === "ADMIN" && <Link href="/admin" className="mr-3 hover:text-orange-400">Admin</Link>}
              {user ? <span className="space-x-3"><span>{user.display_name}</span><LogoutButton /></span> : <span className="space-x-3"><Link href="/login">Giriş Yap</Link><Link href="/register">Kayıt Ol</Link></span>}
            </span>
          </div>
        </header>

        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
          {children}
        </main>

        <footer className="border-t border-neutral-800 py-6">
          <p className="mx-auto max-w-5xl px-4 text-center text-xs text-neutral-600">
            Yomiba — Fiyatlar kamuya açık mağaza sayfalarından toplanır ve
            gecikmeli olabilir.
          </p>
        </footer>
      </body>
    </html>
  );
}
