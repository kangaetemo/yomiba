import { notFound, permanentRedirect } from "next/navigation";
import { ApiError } from "@/lib/api";
import { volumePath } from "@/lib/paths";
import { getVolume } from "@/services/catalog";

export const dynamic = "force-dynamic";

/** Old number-based volume links land on /series/<slug>/cilt-<n>. */
export default async function LegacyVolumePage({ params }: { params: Promise<{ id: string }> }) {
  const numId = Number((await params).id);
  if (!Number.isInteger(numId) || numId <= 0) notFound();
  let detail;
  try {
    detail = await getVolume(numId);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
  permanentRedirect(volumePath(detail.series.slug, detail.number));
}
