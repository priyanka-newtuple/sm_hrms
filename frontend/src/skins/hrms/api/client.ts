import axios from "axios";

import { isPublicPath, loginPath } from "@/skins/hrms/auth/session";

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_HRMS_API_BASE_URL || "/api/v1",
  withCredentials: true, // session lives in an httpOnly cookie
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const requestUrl: string = error.config?.url ?? "";
      // /auth/me 401s when there is no session — expected on public pages.
      const isSessionProbe = requestUrl.includes("/auth/me");
      if (!isSessionProbe && !isPublicPath(window.location.pathname)) {
        window.location.assign(loginPath(`${window.location.pathname}${window.location.search}`));
      }
    }
    return Promise.reject(error);
  },
);
