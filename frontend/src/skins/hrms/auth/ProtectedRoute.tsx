import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "./AuthContext";
import { loginPath } from "./session";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div className="flex h-screen items-center justify-center text-gray-600">Loading…</div>;
  }
  if (!user) {
    return <Navigate to={loginPath(`${location.pathname}${location.search}`)} replace />;
  }
  return <>{children}</>;
}

export function RequirePermission({
  featureKey,
  action,
  children,
}: {
  featureKey: string;
  action: string;
  children: ReactNode;
}) {
  const { user } = useAuth();
  const grant = user?.permissions.find((p) => p.feature_key === featureKey);
  const allowed =
    !!grant &&
    (grant.actions.includes("full") ||
      grant.actions.includes(action) ||
      (grant.actions.includes("manage") && ["view", "create", "edit"].includes(action)));

  if (!allowed) {
    return (
      <div className="p-8 text-gray-600">
        You don&apos;t have permission to view this page.
      </div>
    );
  }
  return <>{children}</>;
}
