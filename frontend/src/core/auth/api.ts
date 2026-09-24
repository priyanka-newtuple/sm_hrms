import type {
  TokenResponse,
  LoginCredentials,
  RegisterCredentials,
  RegisterWithOrgCredentials,
  PendingOrgRegistrationResponse,
  GoogleAuthCallback,
  MicrosoftAuthCallback,
  MicrosoftAuthUrlResponse,
  MicrosoftTokenResponse,
  User,
  UserPublic,
  UserRole,
  OrganizationPublic,
  UserOrganizationsResponse,
} from './types';
import { env } from '../../skins/skin.config';

const API_BASE = env.apiBase;

// API returns snake_case, we use camelCase in frontend
interface ApiUserResponse {
  id: string;
  email: string;
  full_name: string;
  avatar_url?: string;
  role: string;
  auth_type: string;
  organization_id?: string;
  is_active?: boolean;
  last_login_at?: string;
  created_at?: string;
  updated_at?: string;
}

interface ApiOrganizationResponse {
  id: string;
  name: string;
  slug: string;
  logo_url?: string;
  domain?: string;
  settings?: Record<string, unknown>;
  status?: string;
  created_at?: string;
  updated_at?: string;
}

interface ApiUserOrganizationMembership {
  id: string | null;
  organization_id: string;
  organization_name: string;
  organization_slug: string;
  organization_domain: string | null;
  organization_logo_url: string | null;
  organization_status: string;
  role: string;
  status: string;
  is_current: boolean;
}

interface ApiUserOrganizationsResponse {
  organizations: ApiUserOrganizationMembership[];
  current_organization_id: string | null;
}

interface ApiTokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: ApiUserResponse;
}

interface ApiMicrosoftTokenResponse {
  token_type: string;
  id_token: string;
  access_token?: string;
  expires_in?: number;
  user: ApiUserResponse;
  app_access_token?: string;
  app_refresh_token?: string;
}

function transformUser(apiUser: ApiUserResponse): UserPublic {
  return {
    id: apiUser.id,
    email: apiUser.email,
    fullName: apiUser.full_name,
    avatarUrl: apiUser.avatar_url,
    role: apiUser.role as UserPublic['role'],
    authType: apiUser.auth_type as UserPublic['authType'],
    organizationId: apiUser.organization_id,
  };
}

function transformOrganization(apiOrg: ApiOrganizationResponse): OrganizationPublic {
  return {
    id: apiOrg.id,
    name: apiOrg.name,
    slug: apiOrg.slug,
    logoUrl: apiOrg.logo_url,
    settings: apiOrg.settings,
  };
}

function transformUserOrganizations(
  apiResponse: ApiUserOrganizationsResponse
): UserOrganizationsResponse {
  return {
    organizations: apiResponse.organizations.map((org) => ({
      id: org.id,
      organizationId: org.organization_id,
      organizationName: org.organization_name,
      organizationSlug: org.organization_slug,
      organizationDomain: org.organization_domain ?? null,
      organizationLogoUrl: org.organization_logo_url ?? null,
      organizationStatus: org.organization_status,
      role: org.role as UserRole,
      status: org.status,
      isCurrent: org.is_current,
    })),
    currentOrganizationId: apiResponse.current_organization_id,
  };
}

function transformTokenResponse(apiResponse: ApiTokenResponse): TokenResponse {
  return {
    access_token: apiResponse.access_token,
    refresh_token: apiResponse.refresh_token,
    token_type: apiResponse.token_type,
    user: transformUser(apiResponse.user),
  };
}

function transformMicrosoftTokenResponse(
  apiResponse: ApiMicrosoftTokenResponse
): MicrosoftTokenResponse {
  return {
    token_type: apiResponse.token_type,
    id_token: apiResponse.id_token,
    access_token: apiResponse.access_token,
    expires_in: apiResponse.expires_in,
    user: transformUser(apiResponse.user),
  };
}

// Token storage
const ACCESS_TOKEN_KEY = 'ats_access_token';
const REFRESH_TOKEN_KEY = 'ats_refresh_token';
const MICROSOFT_ID_TOKEN_KEY = 'ats_ms_id_token';
const MICROSOFT_ACCESS_TOKEN_KEY = 'ats_ms_access_token';
const SESSION_PROVIDER_KEY = 'ats_session_provider';
const AUTH_USER_CACHE_KEY = 'ats_auth_user_cache';

type SessionProvider = 'app' | 'microsoft' | null;

let accessToken: string | null = null;

function setSessionProvider(provider: SessionProvider): void {
  if (provider) {
    localStorage.setItem(SESSION_PROVIDER_KEY, provider);
  } else {
    localStorage.removeItem(SESSION_PROVIDER_KEY);
  }
}

export function getSessionProvider(): SessionProvider {
  const value = localStorage.getItem(SESSION_PROVIDER_KEY);
  if (value === 'app' || value === 'microsoft') return value;
  return null;
}

function cacheAuthUser(user: UserPublic | null): void {
  if (!user) {
    localStorage.removeItem(AUTH_USER_CACHE_KEY);
    return;
  }
  localStorage.setItem(AUTH_USER_CACHE_KEY, JSON.stringify(user));
}

export function getCachedAuthUser(): UserPublic | null {
  const raw = localStorage.getItem(AUTH_USER_CACHE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as UserPublic;
  } catch {
    return null;
  }
}

export function getAccessToken(): string | null {
  if (accessToken) return accessToken;
  const provider = getSessionProvider();
  if (provider === 'microsoft') {
    return localStorage.getItem(MICROSOFT_ID_TOKEN_KEY);
  }
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
  if (token) {
    setSessionProvider('app');
    localStorage.setItem(ACCESS_TOKEN_KEY, token);
  } else {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
  }
  // Dispatch custom event for same-tab token changes
  window.dispatchEvent(new Event('token-changed'));
}

export function getRefreshToken(): string | null {
  if (getSessionProvider() !== 'app') return null;
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setRefreshToken(token: string | null): void {
  if (token) {
    localStorage.setItem(REFRESH_TOKEN_KEY, token);
  } else {
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  }
}

function isHttpError(err: unknown): err is { status: number } {
  return typeof err === 'object' && err !== null && 'status' in err;
}

export function clearTokens(): void {
  accessToken = null;
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(MICROSOFT_ID_TOKEN_KEY);
  localStorage.removeItem(MICROSOFT_ACCESS_TOKEN_KEY);
  setSessionProvider(null);
  cacheAuthUser(null);
  // Dispatch custom event for same-tab token changes
  window.dispatchEvent(new Event('token-changed'));
}

function setMicrosoftTokens(idToken: string, accessTokenValue?: string): void {
  accessToken = idToken;
  setSessionProvider('microsoft');
  localStorage.setItem(MICROSOFT_ID_TOKEN_KEY, idToken);
  if (accessTokenValue) {
    localStorage.setItem(MICROSOFT_ACCESS_TOKEN_KEY, accessTokenValue);
  } else {
    localStorage.removeItem(MICROSOFT_ACCESS_TOKEN_KEY);
  }
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  window.dispatchEvent(new Event('token-changed'));
}

/**
 * Caches the raw Microsoft id_token under its own storage key, without any
 * of setMicrosoftTokens' side effects (session provider, in-memory access
 * token, clearing the app token). This exists purely so a skin can bridge
 * this token into an external system that only trusts a real Microsoft-
 * signed id_token — the SM's own app_access_token remains the actor's
 * primary session token regardless of whether this is also cached.
 */
export function cacheMicrosoftIdToken(idToken: string): void {
  localStorage.setItem(MICROSOFT_ID_TOKEN_KEY, idToken);
}

// Custom error class for pending approval status (login)
export class PendingApprovalError extends Error {
  constructor(message: string = 'Account is pending approval') {
    super(message);
    this.name = 'PendingApprovalError';
  }
}

// Custom error class for registration pending approval (new registration flow)
export class RegistrationPendingError extends Error {
  public readonly userId: string;
  public readonly organizationId: string;
  public readonly organizationName: string;
  public readonly approvalType: 'pending_org_admin' | 'pending_platform';
  public readonly isNewOrganization: boolean;

  constructor(
    message: string,
    data: {
      userId: string;
      organizationId: string;
      organizationName: string;
      approvalType: 'pending_org_admin' | 'pending_platform';
      isNewOrganization: boolean;
    }
  ) {
    super(message);
    this.name = 'RegistrationPendingError';
    this.userId = data.userId;
    this.organizationId = data.organizationId;
    this.organizationName = data.organizationName;
    this.approvalType = data.approvalType;
    this.isNewOrganization = data.isNewOrganization;
  }
}

// API response for pending registration
interface ApiRegistrationResponse {
  message: string;
  user_id: string;
  organization_id: string;
  organization_name: string;
  approval_type: 'active' | 'pending_org_admin' | 'pending_platform';
  is_new_organization: boolean;
}

async function authRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;

  // Extract headers from options to merge properly
  const { headers: optionHeaders, ...restOptions } = options;

  const response = await fetch(url, {
    ...restOptions,
    headers: {
      'Content-Type': 'application/json',
      ...(optionHeaders as Record<string, string>),
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const rawDetail = errorData.detail;

    // FastAPI 422 returns `detail` as an array of validation errors.
    // HTTPException returns `detail` as a string. Normalize both shapes.
    const detail =
      typeof rawDetail === 'string'
        ? rawDetail
        : Array.isArray(rawDetail)
          ? rawDetail.map((e) => e?.msg || JSON.stringify(e)).join('; ')
          : '';

    // Check for pending approval status (from both 202 and 403 responses)
    // Login returns: "Your account is pending approval..."
    // Register returns: "pending_approval"
    if (
      detail === 'pending_approval' ||
      detail.toLowerCase().includes('pending approval') ||
      response.status === 202
    ) {
      throw new PendingApprovalError();
    }

    throw new Error(detail || `Request failed: ${response.status}`);
  }

  return response.json();
}

export const authApi = {
  login: async (credentials: LoginCredentials): Promise<TokenResponse> => {
    const apiResponse = await authRequest<ApiTokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(credentials),
    });
    setAccessToken(apiResponse.access_token);
    setRefreshToken(apiResponse.refresh_token);
    const transformed = transformTokenResponse(apiResponse);
    cacheAuthUser(transformed.user);
    return transformed;
  },

  register: async (credentials: RegisterCredentials): Promise<TokenResponse> => {
    const url = `${API_BASE}/auth/register`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(credentials),
    });

    const data = await response.json();

    // Handle 202 Accepted - user is pending approval
    if (response.status === 202) {
      const regData = data as ApiRegistrationResponse;
      throw new RegistrationPendingError(regData.message, {
        userId: regData.user_id,
        organizationId: regData.organization_id,
        organizationName: regData.organization_name,
        approvalType: regData.approval_type as 'pending_org_admin' | 'pending_platform',
        isNewOrganization: regData.is_new_organization,
      });
    }

    // Handle errors
    if (!response.ok) {
      const detail = data.detail || '';
      if (detail === 'pending_approval' || detail.toLowerCase().includes('pending approval')) {
        throw new PendingApprovalError();
      }
      throw new Error(detail || `Request failed: ${response.status}`);
    }

    // Handle 201 Created - user is active
    const apiResponse = data as ApiTokenResponse;
    setAccessToken(apiResponse.access_token);
    setRefreshToken(apiResponse.refresh_token);
    const transformed = transformTokenResponse(apiResponse);
    cacheAuthUser(transformed.user);
    return transformed;
  },

  registerWithOrg: async (
    credentials: RegisterWithOrgCredentials
  ): Promise<PendingOrgRegistrationResponse> => {
    const response = await authRequest<PendingOrgRegistrationResponse>(
      '/auth/register-with-org',
      {
        method: 'POST',
        body: JSON.stringify(credentials),
      }
    );
    return response;
  },

  refresh: async (): Promise<TokenResponse | null> => {
    if (getSessionProvider() !== 'app') return null;
    const refreshToken = getRefreshToken();
    if (!refreshToken) return null;

    try {
      const apiResponse = await authRequest<ApiTokenResponse>('/auth/refresh', {
        method: 'POST',
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      setAccessToken(apiResponse.access_token);
      setRefreshToken(apiResponse.refresh_token);
      const transformed = transformTokenResponse(apiResponse);
      cacheAuthUser(transformed.user);
      return transformed;
    } catch (err) {
      // Only clear tokens on a definitive auth rejection (401/403).
      // Network errors, timeouts, or server errors (5xx) should not log the user out —
      // the refresh token is still valid and the next request can retry.
      const status = isHttpError(err) ? err.status : undefined;
      if (status === 401 || status === 403) {
        clearTokens();
      }
      return null;
    }
  },

  logout: async (): Promise<void> => {
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      try {
        await authRequest('/auth/logout', {
          method: 'POST',
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
      } catch {
        // Ignore logout errors
      }
    }
    clearTokens();
  },

  getMe: async (): Promise<User> => {
    const token = getAccessToken();
    if (!token) throw new Error('Not authenticated');

    const apiResponse = await authRequest<ApiUserResponse>('/auth/me', {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    const user: User = {
      id: apiResponse.id,
      email: apiResponse.email,
      fullName: apiResponse.full_name,
      avatarUrl: apiResponse.avatar_url,
      role: apiResponse.role as User['role'],
      authType: apiResponse.auth_type as User['authType'],
      organizationId: apiResponse.organization_id,
      isActive: apiResponse.is_active ?? true,
      lastLoginAt: apiResponse.last_login_at,
      createdAt: apiResponse.created_at ?? '',
      updatedAt: apiResponse.updated_at,
    };
    cacheAuthUser({
      id: user.id,
      email: user.email,
      fullName: user.fullName,
      avatarUrl: user.avatarUrl,
      role: user.role,
      authType: user.authType,
      organizationId: user.organizationId,
    });
    return user;
  },

  getCurrentOrganization: async (): Promise<OrganizationPublic | null> => {
    const token = getAccessToken();
    if (!token) return null;

    try {
      const apiResponse = await authRequest<ApiOrganizationResponse>(
        '/organizations/current',
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );
      return transformOrganization(apiResponse);
    } catch {
      // User might not have an organization yet
      return null;
    }
  },

  getGoogleAuthUrl: async (redirectUri?: string): Promise<string> => {
    const params = redirectUri ? `?redirect_uri=${encodeURIComponent(redirectUri)}` : '';
    const response = await authRequest<{ url: string }>(`/auth/google/url${params}`);
    return response.url;
  },

  getMicrosoftAuthUrl: async (redirectUri?: string): Promise<MicrosoftAuthUrlResponse> => {
    const params = redirectUri ? `?redirect_uri=${encodeURIComponent(redirectUri)}` : '';
    return authRequest<MicrosoftAuthUrlResponse>(`/auth/microsoft/url${params}`);
  },

  googleCallback: async (data: GoogleAuthCallback): Promise<TokenResponse> => {
    const url = `${API_BASE}/auth/google/callback`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });

    const responseData = await response.json();

    // Handle 202 Accepted - user is pending approval
    if (response.status === 202) {
      const regData = responseData as ApiRegistrationResponse;
      throw new RegistrationPendingError(regData.message, {
        userId: regData.user_id,
        organizationId: regData.organization_id,
        organizationName: regData.organization_name,
        approvalType: regData.approval_type as 'pending_org_admin' | 'pending_platform',
        isNewOrganization: regData.is_new_organization,
      });
    }

    // Handle errors
    if (!response.ok) {
      const detail = responseData.detail || '';
      if (detail === 'pending_approval' || detail.toLowerCase().includes('pending approval')) {
        throw new PendingApprovalError();
      }
      throw new Error(detail || `Request failed: ${response.status}`);
    }

    // Handle 200/201 - user is active, got tokens
    const apiResponse = responseData as ApiTokenResponse;
    setAccessToken(apiResponse.access_token);
    setRefreshToken(apiResponse.refresh_token);
    const transformed = transformTokenResponse(apiResponse);
    cacheAuthUser(transformed.user);
    return transformed;
  },

  microsoftCallback: async (data: MicrosoftAuthCallback): Promise<MicrosoftTokenResponse> => {
    const url = `${API_BASE}/auth/microsoft/callback`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });

    const responseData = await response.json();

    if (response.status === 202) {
      const regData = responseData as ApiRegistrationResponse;
      throw new RegistrationPendingError(regData.message, {
        userId: regData.user_id,
        organizationId: regData.organization_id,
        organizationName: regData.organization_name,
        approvalType: regData.approval_type as 'pending_org_admin' | 'pending_platform',
        isNewOrganization: regData.is_new_organization,
      });
    }

    if (!response.ok) {
      const detail = responseData.detail || '';
      if (detail === 'pending_approval' || detail.toLowerCase().includes('pending approval')) {
        throw new PendingApprovalError();
      }
      throw new Error(detail || `Request failed: ${response.status}`);
    }

    const apiResponse = responseData as ApiMicrosoftTokenResponse;
    // Prefer app-issued JWTs so all API routes (including legacy) accept the token
    if (apiResponse.app_access_token) {
      setAccessToken(apiResponse.app_access_token);
      if (apiResponse.app_refresh_token) {
        setRefreshToken(apiResponse.app_refresh_token);
      }
    } else {
      setMicrosoftTokens(apiResponse.id_token, apiResponse.access_token);
    }
    // Cache the raw Microsoft id_token regardless of which branch above ran —
    // some external systems (e.g. a skin bridging to a legacy backend that
    // only validates real Microsoft-signed tokens) need it even when the
    // app-issued JWT is the platform's own primary session token.
    if (apiResponse.id_token) {
      cacheMicrosoftIdToken(apiResponse.id_token);
    }
    const transformed = transformMicrosoftTokenResponse(apiResponse);
    cacheAuthUser(transformed.user);
    return transformed;
  },

  getMyOrganizations: async (): Promise<UserOrganizationsResponse> => {
    const token = getAccessToken();
    if (!token) throw new Error('Not authenticated');

    const apiResponse = await authRequest<ApiUserOrganizationsResponse>(
      '/users/me/organizations',
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      }
    );
    return transformUserOrganizations(apiResponse);
  },

  switchOrganization: async (organizationId: string): Promise<void> => {
    const token = getAccessToken();
    if (!token) throw new Error('Not authenticated');

    const response = await authRequest<{
      message: string;
      access_token?: string;
      token_type?: string;
      organization_id?: string;
      organization_name?: string;
    }>('/users/me/organizations/switch', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ organization_id: organizationId }),
    });
    // Rotate the access token so the organization_id claim reflects the new org.
    // Without this, every tenancy-scoped request would keep reading the old org.
    if (response.access_token) {
      setAccessToken(response.access_token);
    }
    const current = getCachedAuthUser();
    if (current) {
      cacheAuthUser({ ...current, organizationId });
    }
  },

  forgotPassword: async (email: string): Promise<{ message: string }> => {
    return authRequest<{ message: string }>('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email }),
    });
  },

  resetPassword: async (token: string, newPassword: string): Promise<{ message: string }> => {
    return authRequest<{ message: string }>('/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify({ token, new_password: newPassword }),
    });
  },
};
