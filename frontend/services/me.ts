import { getJson } from "@/lib/api";
import type { MyCollectionItem, MyPriceAlert, MyStockAlert, MyWishlistItem } from "@/types";

export const getMyCollection = () => getJson<MyCollectionItem[]>("/me/collection");
export const getMyWishlist = () => getJson<MyWishlistItem[]>("/me/wishlist");
export const getMyPriceAlerts = () => getJson<MyPriceAlert[]>("/me/price-alerts");
export const getMyStockAlerts = () => getJson<MyStockAlert[]>("/me/stock-alerts");
