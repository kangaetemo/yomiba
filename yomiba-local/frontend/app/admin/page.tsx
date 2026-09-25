import type { Metadata } from "next";
import { AdminControls } from "@/components/admin/AdminControls";

export const metadata: Metadata = {
  title: "Admin",
};

export default function AdminPage() {
  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight text-neutral-50">
          İçe aktarma ve senkron
        </h1>
        <p className="text-sm text-neutral-500">
          Katalog senkronunu manuel çalıştırın, mağaza içe aktarın ve son
          denemeleri izleyin.
        </p>
      </header>
      <AdminControls />
    </div>
  );
}
