import { ApiError, getJson, postJson } from "@/lib/api";
import { unstable_rethrow } from "next/navigation";

export type CurrentUser = {
  id: number;
  email: string;
  display_name: string;
  role: "USER" | "ADMIN";
};

export const getMe = () => getJson<CurrentUser>("/auth/me");
export const login = (email: string, password: string) =>
  postJson<CurrentUser>("/auth/login", { email, password });
export const register = (email: string, password: string, display_name: string) =>
  postJson<CurrentUser>("/auth/register", { email, password, display_name });

/**
 * Current user for chrome (header) rendering. When the backend
 * is unreachable or answers with an unexpected error, the page renders as
 * logged out instead of the whole site failing with a 500. Next.js rendering
 * control signals still propagate to the framework.
 */
export async function currentUserOrNull(): Promise<CurrentUser | null> {
  try {
    return await currentUser();
  } catch (error) {
    unstable_rethrow(error);
    console.error("currentUser failed; rendering as anonymous", error);
    return null;
  }
}

export async function currentUser(): Promise<CurrentUser | null> {
  try {
    return await getMe();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}
