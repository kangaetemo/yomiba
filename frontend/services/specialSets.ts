import { deleteJson, getJson, patchJson, postJson } from "@/lib/api";

export type AdminSpecialSet = {
  id: number; title: string; store: string; product_url: string; image_url: string | null;
  price: number | null; in_stock: boolean | null; preorder: boolean; active: boolean;
  last_checked: string | null; check_error: string | null;
  series: { id: number; title: string; slug: string | null }[];
};

export type SeriesOption = { id: number; title: string };

export const getSpecialSets = () => getJson<{ items: AdminSpecialSet[] }>("/admin/special-sets");
export const getSeriesOptions = () => getJson<{ items: SeriesOption[] }>("/admin/special-sets/series");
export const createSpecialSet = (input: { product_url: string; series_ids: number[]; title?: string; preorder: boolean }) =>
  postJson<AdminSpecialSet>("/admin/special-sets", input);
export const updateSpecialSet = (id: number, input: Partial<{ title: string; series_ids: number[]; preorder: boolean; active: boolean }>) =>
  patchJson<AdminSpecialSet>(`/admin/special-sets/${id}`, input);
export const refreshSpecialSet = (id: number) => postJson<AdminSpecialSet>(`/admin/special-sets/${id}/refresh`);
export const deleteSpecialSet = (id: number) => deleteJson<{ deleted: number }>(`/admin/special-sets/${id}`);
