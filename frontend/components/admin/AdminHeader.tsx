import { redirect } from "next/navigation";
import { currentUser } from "@/services/auth";

/** Sends anyone but an admin away; `path` is where login returns to. */
export async function requireAdmin(path: string): Promise<void> {
  const user = await currentUser();
  if (!user) redirect(`/login?next=${encodeURIComponent(path)}`);
  if (user.role !== "ADMIN") redirect("/");
}

/** Page title + one-paragraph explanation, the same on every admin page. */
export function AdminHeader({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <header className="space-y-1">
      <h1 className="text-2xl font-bold tracking-tight text-ink">{title}</h1>
      {children && <p className="max-w-3xl text-sm text-muted">{children}</p>}
    </header>
  );
}
