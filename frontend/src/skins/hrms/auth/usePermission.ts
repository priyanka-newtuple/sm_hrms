import { useAuth } from "./AuthContext";

/**
 * Mirrors the backend authz shape purely for UI affordance (hide/disable a
 * button, hide a nav item). The server independently re-checks every
 * request via app.authz.deps.require_permission — this hook is never the
 * enforcement boundary, only a convenience so the UI doesn't show actions
 * that would 403.
 */
export function usePermission(featureKey: string, action: string): boolean {
  const { user } = useAuth();
  if (!user) return false;
  const grant = user.permissions.find((p) => p.feature_key === featureKey);
  if (!grant) return false;
  if (grant.actions.includes("full")) return true;
  if (grant.actions.includes("manage") && ["view", "create", "edit"].includes(action)) return true;
  return grant.actions.includes(action);
}

export function useFeatureScope(featureKey: string): string | null {
  const { user } = useAuth();
  return user?.permissions.find((p) => p.feature_key === featureKey)?.record_scope ?? null;
}

export function useHasPermissionKey(key: string): boolean {
  const { user } = useAuth();
  return user?.permission_keys.includes(key) ?? false;
}
