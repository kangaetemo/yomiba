"use client";

import { useRouter } from "next/navigation";

export function LogoutButton({ className = "" }: { className?: string }) {
  const router = useRouter();
  return <button type="button" onClick={async () => {
    const response = await fetch("/api/auth/logout", { method: "POST" });
    if (response.ok) { router.push("/"); router.refresh(); }
  }} className={`whitespace-nowrap hover:text-accent ${className}`}>Çıkış Yap</button>;
}
