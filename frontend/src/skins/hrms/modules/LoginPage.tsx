import { useEffect, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";

import { authApi, type DevUser } from "@/skins/hrms/api/auth";
import curves from "@/skins/hrms/assets/geometric-curves-strip.png";
import loginBg from "@/skins/hrms/assets/login_page.png";
import { useAuth } from "@/skins/hrms/auth/AuthContext";
import { safeNextPath } from "@/skins/hrms/auth/session";
import { Button } from "@/skins/hrms/components/Button";
import { PublicTopNav } from "@/skins/hrms/components/PublicTopNav";

export default function LoginPage() {
  const { user, loading, refresh } = useAuth();
  const [searchParams] = useSearchParams();
  const afterLogin = safeNextPath(searchParams.get("next")) ?? "/";
  const oauthError = searchParams.get("error");
  const [devUsers, setDevUsers] = useState<DevUser[]>([]);
  const [loginMode, setLoginMode] = useState<"demo" | "dev" | null>(null);
  const [loggingIn, setLoggingIn] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.allSettled([authApi.demoUsers(), authApi.devUsers()]).then(([demo, dev]) => {
      if (demo.status === "fulfilled" && demo.value.length > 0) {
        setDevUsers(demo.value);
        setLoginMode("demo");
      } else if (dev.status === "fulfilled" && dev.value.length > 0) {
        setDevUsers(dev.value);
        setLoginMode("dev");
      } else {
        setDevUsers([]);
        setLoginMode(null);
      }
    });
  }, []);

  if (!loading && user) return <Navigate to={afterLogin} replace />;

  async function handleDevLogin(email: string) {
    setError(null);
    setLoggingIn(email);
    try {
      if (loginMode === "demo") await authApi.demoLogin(email);
      else await authApi.devLogin(email);
      await refresh();
    } catch {
      setError("Login failed.");
    } finally {
      setLoggingIn(null);
    }
  }

  return (
    <div className="relative flex h-dvh flex-col overflow-hidden">
      <img src={loginBg} alt="" className="absolute inset-0 h-full w-full object-cover" />
      <div className="absolute inset-0 bg-gradient-to-r from-gray-900/50 via-gray-900/20 to-transparent" />

      <PublicTopNav />

      <div className="relative z-10 flex min-h-0 flex-1 items-center justify-center overflow-hidden px-4 py-3 sm:px-8 lg:justify-start lg:px-12 xl:px-20">
        <div className="flex max-h-full w-full max-w-xl flex-col overflow-hidden rounded-card bg-white shadow-2xl">
          <div className="shrink-0 px-8 pt-8 text-center">
            <h1 className="mx-auto w-fit">
              <span className="-mr-[0.28em] block bg-cobalt-gradient bg-clip-text text-5xl font-light leading-none tracking-[0.28em] text-transparent sm:text-6xl">
                HRMS
              </span>
              <span aria-hidden className="mt-2.5 block h-[3px] w-full bg-cobalt-gradient" />
            </h1>
          </div>

          <div className="shrink-0 px-8 pt-4">
            <a href={authApi.googleLoginUrl(afterLogin === "/" ? null : afterLogin)}>
              <Button className="w-full">Sign in with your Newtuple Account</Button>
            </a>
          </div>

          {devUsers.length > 0 && (
            <div className="mx-8 mt-4 min-h-0 border-t border-gray-200 pt-3">
              <p className="mb-2 text-xs font-medium uppercase tracking-wider text-gray-600">
                {loginMode === "demo" ? "Demo role logins" : "Test as a role (local only)"}
              </p>
              <div className="max-h-[min(18rem,calc(100dvh-28rem))] space-y-0.5 overflow-y-auto">
                {devUsers.map((u) => (
                  <button
                    key={u.email}
                    onClick={() => handleDevLogin(u.email)}
                    disabled={loggingIn !== null}
                    className="flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left transition-colors duration-hover ease-brand hover:bg-gray-50"
                  >
                    <span className="text-sm font-medium text-gray-900">{u.role_name}</span>
                    <span className="truncate text-xs text-gray-600">
                      {loggingIn === u.email ? "Signing in…" : u.full_name}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
          {(error || oauthError) && (
            <p className="shrink-0 px-8 pt-2 text-center text-sm text-danger">{error || oauthError}</p>
          )}

          <img src={curves} alt="" className="pointer-events-none mt-2 w-full shrink-0" />
        </div>
      </div>
    </div>
  );
}
