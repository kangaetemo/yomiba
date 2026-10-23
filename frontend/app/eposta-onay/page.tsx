import type { Metadata } from "next";
import { EmailTokenConfirm } from "@/components/EmailTokenConfirm";

export const metadata: Metadata = { title: "E-posta onayı", robots: { index: false } };

export default async function Page({ searchParams }: { searchParams: Promise<{ t?: string }> }) {
  const { t } = await searchParams;
  return <EmailTokenConfirm token={t ?? ""} />;
}
