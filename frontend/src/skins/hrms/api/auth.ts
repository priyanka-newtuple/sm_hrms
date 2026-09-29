import { apiClient } from "./client";
import type { CurrentUser } from "./types";

export interface DevUser {
  email: string;
  full_name: string;
  role_name: string;
  department: string;
}

export const authApi = {
  me: () => apiClient.get<CurrentUser>("/auth/me").then((r) => r.data),
  devUsers: () => apiClient.get<DevUser[]>("/auth/dev-users").then((r) => r.data),
  devLogin: (email: string) => apiClient.post("/auth/dev-login", { email }).then((r) => r.data),
  demoUsers: () => apiClient.get<DevUser[]>("/auth/demo-users").then((r) => r.data),
  demoLogin: (email: string) => apiClient.post("/auth/demo-login", { email }).then((r) => r.data),
  logout: () => apiClient.post("/auth/logout").then((r) => r.data),
  googleLoginUrl: (next?: string | null) => {
    const base = `${apiClient.defaults.baseURL}/auth/google/login`;
    return next ? `${base}?next=${encodeURIComponent(next)}` : base;
  },
};
