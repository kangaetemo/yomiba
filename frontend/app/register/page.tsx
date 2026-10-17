import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { AuthForm } from "@/components/AuthForm";
import { currentUserOrNull, safeNext } from "@/services/auth";

export const metadata: Metadata = { title: "Hesap oluştur", robots: { index: false } };

export default async function Page({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  // Already signed in: nothing to do here.
  if (await currentUserOrNull()) redirect(safeNext(next) ?? "/");
  return <AuthForm mode="register" next={safeNext(next) ?? undefined} />;
}
