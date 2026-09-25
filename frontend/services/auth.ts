import { ApiError, getJson, postJson } from "@/lib/api";

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

export async function currentUser(): Promise<CurrentUser | null> {
  try {
    return await getMe();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}
