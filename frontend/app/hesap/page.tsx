import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { AccountSettings } from "@/components/AccountSettings";
import { currentUser } from "@/services/auth";

export const metadata: Metadata = { title: "Hesap ayarları", robots: { index: false } };

export default async function AccountPage() {
  const user = await currentUser();
  if (!user) redirect("/login?next=%2Fhesap");
  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <header className="space-y-2">
        <p className="eyebrow">Hesabın</p>
        <h1 className="text-3xl font-semibold text-ink sm:text-4xl">Hesap ayarları</h1>
      </header>
      <AccountSettings user={user} />
    </div>
  );
}
