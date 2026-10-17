import { redirect } from "next/navigation";

/** The former ISBN review centre now lives in the health report. */
export default function IsbnPage() {
  redirect("/admin/isbn/saglik");
}
