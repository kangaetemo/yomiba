"use client";

import { useRouter } from "next/navigation";

export function LogoutButton() {
  const router = useRouter();
  return <button onClick={async () => {
    const response = await fetch("/api/auth/logout", { method: "POST" });
    if (response.ok) { router.push("/"); router.refresh(); }
  }} className="hover:text-accent">Çıkış Yap</button>;
}
