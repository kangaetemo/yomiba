import type { Metadata } from "next";
import { AdminControls } from "@/components/admin/AdminControls";
import { currentUser } from "@/services/auth";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
  title: "Admin",
};

export default async function AdminPage() {
  const user = await currentUser();
  if (!user) redirect("/login");
  if (user.role !== "ADMIN") redirect("/");
  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight text-ink">
          İçe aktarma ve senkron
        </h1>
        <p className="text-sm text-muted">
          Katalog senkronunu manuel çalıştırın, mağaza içe aktarın ve son
          denemeleri izleyin.
        </p>
      </header>
      <AdminControls />
    </div>
  );
}
