import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';
import { flushSync } from 'react-dom';
import type {
  AuthContextType,
  UserPublic,
  OrganizationPublic,
  UserOrganizationMembership,
} from './types';
import { authApi, getAccessToken, clearTokens } from './api';
import { roles as rolesApi } from '../services/api';
import type { PermissionsSummary } from '../types/rbac';
import { env } from '../../skins/skin.config';
import {
  applyMode,
  applyTheme,
  getStoredPreference,
  resetTheme,
  resolveMode,
  setDarkAllowed,
  themeFromSettings,
} from '../theme';
import { featureFlagsFromSettings } from '../hooks/useFeatureFlags';
import { resolveActiveSkin } from '../../skins/registry';

const AuthContext = createContext<AuthContextType | null>(null);
const BYPASS_AUTH = env.bypassAuth;
// Resolved the same way App.tsx resolves the active customer skin — this
// context mounts above SkinProvider, so it can't consume useSkin() and
// instead reads the registry directly to get the skin's theme defaults.
const ACTIVE_SKIN_ID = (import.meta.env.VITE_SKIN_ID as string | undefined)?.trim() ?? 'default';
const ACTIVE_SKIN_DEFAULT_THEME = resolveActiveSkin(ACTIVE_SKIN_ID)?.defaultTheme;
const MS_OAUTH_STATE_KEY = 'ats_ms_oauth_state';
const BYPASS_PERMISSIONS: PermissionsSummary = {
  roles: [],
  permissions: [],
  entity_permissions: {},
  field_permissions: {},
};

const BYPASS_USER: UserPublic = {
  id: 'modular-settings-user',
  email: 'settings-harness@statemachine.local',
  fullName: 'Settings Harness',
  role: 'admin',
  authType: 'local',
  organizationId: env.bypassOrgId,
};

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<UserPublic | null>(BYPASS_AUTH ? BYPASS_USER : null);
  const [organization, setOrganization] = useState<OrganizationPublic | null>(null);
  const [organizations, setOrganizations] = useState<UserOrganizationMembership[]>([]);
  const [isLoading, setIsLoading] = useState(!BYPASS_AUTH);
  const [permissions, setPermissions] = useState<PermissionsSummary | null>(
    BYPASS_AUTH ? BYPASS_PERMISSIONS : null
  );

  const isAuthenticated = BYPASS_AUTH || user !== null;

  // Fetch organization when user changes
  const fetchOrganization = useCallback(async () => {
    if (BYPASS_AUTH) {
      setOrganization(null);
      return;
    }
    if (!user?.organizationId) {
      setOrganization(null);
      return;
    }
    try {
      const org = await authApi.getCurrentOrganization();
      setOrganization(org);
    } catch {
      setOrganization(null);
    }
  }, [user?.organizationId]);

  // Fetch all organizations the user belongs to
  const fetchOrganizations = useCallback(async () => {
    if (BYPASS_AUTH) {
      setOrganizations([]);
      return;
    }
    if (!user) {
      setOrganizations([]);
      return;
    }
    try {
      const response = await authApi.getMyOrganizations();
      setOrganizations(response.organizations);
    } catch {
      setOrganizations([]);
    }
  }, [user]);

  const fetchPermissions = useCallback(async (): Promise<void> => {
    if (BYPASS_AUTH) return;
    try {
      const data = await rolesApi.getMyPermissions();
      setPermissions(data);
    } catch (e) {
      console.warn('[AuthContext] Failed to fetch permissions, using permissive defaults:', e);
      setPermissions({ roles: [], permissions: [], entity_permissions: {}, field_permissions: {} });
    }
  }, []);

  // Check for existing session on mount
  useEffect(() => {
    if (BYPASS_AUTH) {
      setUser(BYPASS_USER);
      setIsLoading(false);
      return;
    }

    const checkAuth = async () => {
      const token = getAccessToken();
      if (!token) {
        setIsLoading(false);
        return;
      }

      try {
        const userData = await authApi.getMe();
        // Only update if the token hasn't changed while we were waiting
        // (guards against OAuth callback racing with this check)
        if (getAccessToken() === token) {
          setUser({
            id: userData.id,
            email: userData.email,
            fullName: userData.fullName,
            avatarUrl: userData.avatarUrl,
            role: userData.role,
            authType: userData.authType,
            organizationId: userData.organizationId,
          });
          await fetchPermissions();
        }
      } catch {
        // Token might be expired, try to refresh
        const refreshResult = await authApi.refresh();
        if (refreshResult) {
          setUser(refreshResult.user);
          await fetchPermissions();
        } else {
          // Only clear tokens if they haven't been replaced by a concurrent OAuth flow
          if (getAccessToken() === token) {
            clearTokens();
          }
        }
      } finally {
        setIsLoading(false);
      }
    };

    checkAuth();
  }, []);

  // Fetch organization when user changes
  useEffect(() => {
    if (user) {
      fetchOrganization();
      fetchOrganizations();
    } else {
      setOrganization(null);
      setOrganizations([]);
    }
  }, [user, fetchOrganization, fetchOrganizations]);

  // Apply the active organization's dark-mode permission and theme. While
  // auth/org are still loading we keep the cached values (applied on first
  // paint) to avoid a flash; we only reset to the defaults once the user is
  // definitively logged out.
  //
  // Order matters: the permission is cached first so `applyMode` can honour it,
  // and the mode is painted before `applyTheme` because the org's brand and
  // surface colors are derived against whichever mode is on the document.
  useEffect(() => {
    if (organization) {
      setDarkAllowed(featureFlagsFromSettings(organization.settings).darkModeEnabled);
      applyMode(resolveMode(getStoredPreference()));
      applyTheme(themeFromSettings(organization.settings, ACTIVE_SKIN_DEFAULT_THEME));
    } else if (!isLoading && !user) {
      resetTheme();
    }
  }, [organization, user, isLoading]);

  const login = useCallback(async (email: string, password: string) => {
    if (BYPASS_AUTH) {
      setUser(BYPASS_USER);
      return;
    }
    const response = await authApi.login({ email, password });
    flushSync(() => setUser(response.user));
    await fetchPermissions();
  }, [fetchPermissions]);

  const register = useCallback(
    async (email: string, password: string, fullName: string, organizationName?: string) => {
      if (BYPASS_AUTH) {
        setUser({
          ...BYPASS_USER,
          email,
          fullName: fullName || BYPASS_USER.fullName,
        });
        return;
      }
      const response = await authApi.register({
        email,
        password,
        full_name: fullName,
        organization_name: organizationName,
      });
      flushSync(() => setUser(response.user));
      await fetchPermissions();
    },
    [fetchPermissions]
  );

  const loginWithGoogle = useCallback(async () => {
    if (BYPASS_AUTH) {
      setUser(BYPASS_USER);
      return;
    }
    try {
      const redirectUri = `${window.location.origin}/auth/google/callback`;
      const url = await authApi.getGoogleAuthUrl(redirectUri);
      window.location.href = url;
    } catch (error) {
      console.error('Failed to get Google auth URL:', error);
      throw error;
    }
  }, []);

  const handleGoogleCallback = useCallback(async (code: string) => {
    if (BYPASS_AUTH) {
      setUser(BYPASS_USER);
      return;
    }
    const redirectUri = `${window.location.origin}/auth/google/callback`;
    const response = await authApi.googleCallback({ code, redirect_uri: redirectUri });
    flushSync(() => setUser(response.user));
    await fetchPermissions();
  }, [fetchPermissions]);

  const loginWithMicrosoft = useCallback(async () => {
    if (BYPASS_AUTH) {
      setUser(BYPASS_USER);
      return;
    }
    try {
      // Clear any stale tokens before redirecting to Microsoft so that
      // checkAuth on the callback page finds no token and exits immediately,
      // preventing a race where stale-token validation clears the new session.
      clearTokens();
      const redirectUri = `${window.location.origin}/auth/microsoft/callback`;
      const response = await authApi.getMicrosoftAuthUrl(redirectUri);
      // Keep a local fallback in case provider callback drops query `state`.
      sessionStorage.setItem(MS_OAUTH_STATE_KEY, response.state);
      window.location.href = response.url;
    } catch (error) {
      console.error('Failed to get Microsoft auth URL:', error);
      throw error;
    }
  }, []);

  const handleMicrosoftCallback = useCallback(async (code: string, state: string) => {
    if (BYPASS_AUTH) {
      setUser(BYPASS_USER);
      return;
    }
    const redirectUri = `${window.location.origin}/auth/microsoft/callback`;
    const response = await authApi.microsoftCallback({ code, state, redirect_uri: redirectUri });
    flushSync(() => setUser(response.user));
    await fetchPermissions();
  }, [fetchPermissions]);

  const logout = useCallback(async () => {
    if (BYPASS_AUTH) {
      setUser(BYPASS_USER);
      return;
    }
    await authApi.logout();
    setUser(null);
    setOrganization(null);
    setPermissions(null);
  }, []);

  const refreshToken = useCallback(async (): Promise<boolean> => {
    if (BYPASS_AUTH) {
      setUser(BYPASS_USER);
      return true;
    }
    const result = await authApi.refresh();
    if (result) {
      setUser(result.user);
      return true;
    }
    setUser(null);
    return false;
  }, []);

  const switchOrganization = useCallback(
    async (orgId: string) => {
      if (BYPASS_AUTH) {
        setUser((current) => current ? { ...current, organizationId: orgId } : { ...BYPASS_USER, organizationId: orgId });
        return;
      }
      await authApi.switchOrganization(orgId);
      // Hard reload so every page-level cache, query, and route-scoped fetch
      // re-runs against the new org. The new access token is already stored.
      window.location.assign('/dashboard');
    },
    []
  );

  const value: AuthContextType = {
    user,
    organization,
    organizations,
    isLoading,
    isAuthenticated,
    login,
    register,
    loginWithGoogle,
    loginWithMicrosoft,
    handleGoogleCallback,
    handleMicrosoftCallback,
    logout,
    refreshToken,
    switchOrganization,
    refreshOrganization: fetchOrganization,
    refreshOrganizations: fetchOrganizations,
    refreshPermissions: fetchPermissions,
    permissions,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
