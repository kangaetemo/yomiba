import { AdminNav } from "@/components/admin/AdminNav";
import { currentUserOrNull } from "@/services/auth";
import { getOpenReportCount } from "@/services/reports";

/**
 * Shared chrome for every admin page: the section menu. Each page still
 * checks the admin role itself (a layout is not re-run on every
 * navigation), so for anyone else this renders the page alone and the
 * page redirects.
 */
export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const user = await currentUserOrNull();
  if (user?.role !== "ADMIN") return children;
  const openReports = await getOpenReportCount().then((r) => r.new).catch(() => null);
  return (
    <>
      <AdminNav openReports={openReports} />
      {children}
    </>
  );
}
