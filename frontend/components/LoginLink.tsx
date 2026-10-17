"use client";

/** LoginLink: a link to /login (or /register) that brings the reader back to
 * the page they were on (``?next=``) after signing in. */

import Link from "next/link";
import { usePathname } from "next/navigation";

export function LoginLink({
  to = "/login",
  className,
  children,
}: {
  to?: "/login" | "/register";
  className?: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const back = pathname && pathname !== "/" && !pathname.startsWith("/login") && !pathname.startsWith("/register");
  return (
    <Link href={back ? `${to}?next=${encodeURIComponent(pathname)}` : to} className={className}>
      {children}
    </Link>
  );
}
