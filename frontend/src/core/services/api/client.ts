/**
 * Core HTTP client: request(), error helpers, auth header injection, token refresh.
 */

import { getAccessToken, authApi, clearTokens, getSessionProvider, getCachedAuthUser } from '../../auth';
import { env } from '../../../skins/skin.config';

export const API_BASE = env.apiBase;
export const BYPASS_AUTH = env.bypassAuth;
export const BYPASS_ORG_ID = env.bypassOrgId;

export interface ApiErrorData {
  status: number;
  statusText: string;
  message?: string;
  detail?: unknown;
}

export function createApiError(data: ApiErrorData): Error {
  const error = new Error(data.message || `${data.status} ${data.statusText}`);
  error.name = 'ApiError';
  (error as Error & ApiErrorData).status = data.status;
  (error as Error & ApiErrorData).statusText = data.statusText;
  (error as Error & ApiErrorData).detail = data.detail;
  return error;
}

export function getApiErrorMessage(error: unknown, fallback = 'Request failed'): string {
  if (error && typeof error === 'object' && 'detail' in error) {
    const detail = (error as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }
    if (Array.isArray(detail)) {
      const message = detail
        .map((item) => {
          if (!item || typeof item !== 'object') return null;
          const msg = 'msg' in item && typeof item.msg === 'string' ? item.msg : null;
          const loc =
            'loc' in item && Array.isArray(item.loc)
              ? item.loc.filter((part: unknown) => part !== 'body').join('.')
              : '';
          if (!msg) return null;
          return loc ? `${loc}: ${msg}` : msg;
        })
        .filter(Boolean)
        .join('; ');
      if (message) return message;
    }
    if (detail && typeof detail === 'object') {
      if (
        'failure_detail' in detail &&
        typeof detail.failure_detail === 'string' &&
        detail.failure_detail.trim()
      ) {
        return detail.failure_detail;
      }
      if ('detail' in detail && typeof detail.detail === 'string' && detail.detail.trim()) {
        return detail.detail;
      }
    }
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

export function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const payloadPart = token.split('.')[1];
    if (!payloadPart) return null;
    const normalized = payloadPart.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized + '='.repeat((4 - (normalized.length % 4)) % 4);
    return JSON.parse(atob(padded)) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export function getCurrentOrganizationId(): string {
  if (BYPASS_AUTH) {
    return BYPASS_ORG_ID;
  }
  const token = getAccessToken();
  if (!token) {
    return BYPASS_ORG_ID;
  }
  const payload = decodeJwtPayload(token);
  const value = payload?.organization_id || payload?.organizationId || payload?.org_id || payload?.orgId;
  const orgId = typeof value === 'string' ? value.trim() : '';
  if (orgId) return orgId;
  const cachedUser = getCachedAuthUser();
  return cachedUser?.organizationId || BYPASS_ORG_ID;
}

let isRefreshing = false;
let refreshPromise: Promise<boolean> | null = null;

async function handleTokenRefresh(): Promise<boolean> {
  if (BYPASS_AUTH) {
    return false;
  }
  if (getSessionProvider() !== 'app') {
    return false;
  }
  if (isRefreshing && refreshPromise) {
    return refreshPromise;
  }

  isRefreshing = true;
  refreshPromise = (async () => {
    try {
      const result = await authApi.refresh();
      return result !== null;
    } catch {
      return false;
    } finally {
      isRefreshing = false;
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

/**
 * Build headers for authenticated API requests.
 *
 * Extracts user ID, org ID, and roles from the JWT payload or cached auth user.
 * Falls back to bypass-mode headers when no token is present and BYPASS_AUTH is set.
 *
 * @returns A headers record containing Authorization, x-user-id, x-org-id, and x-user-roles.
 */
export function buildAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const token = getAccessToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
    const payload = decodeJwtPayload(token);
    const userId = payload?.sub || payload?.user_id || payload?.userId;
    const orgId = payload?.organization_id || payload?.organizationId || payload?.org_id || payload?.orgId;
    const roles = payload?.roles || payload?.role;
    if (typeof userId === 'string' && userId.trim()) headers['x-user-id'] = userId;
    if (typeof orgId === 'string' && orgId.trim()) headers['x-org-id'] = orgId;
    if (Array.isArray(roles)) headers['x-user-roles'] = roles.map(String).join(',');
    else if (typeof roles === 'string' && roles.trim()) headers['x-user-roles'] = roles;
    const cachedUser = getCachedAuthUser();
    if (!headers['x-user-id'] && cachedUser?.id) headers['x-user-id'] = cachedUser.id;
    if (!headers['x-org-id'] && cachedUser?.organizationId) headers['x-org-id'] = cachedUser.organizationId;
    if (!headers['x-user-roles'] && cachedUser?.role) headers['x-user-roles'] = cachedUser.role;
  } else if (BYPASS_AUTH) {
    headers['x-user-id'] = 'modular-dev-user';
    headers['x-org-id'] = BYPASS_ORG_ID;
    headers['x-user-roles'] = 'admin';
  }
  return headers;
}

export function uploadFile(
  typeId: string,
  file: File,
  extraParams?: Record<string, string>
): Promise<Record<string, unknown>> {
  const params = new URLSearchParams({ type_id: typeId });
  if (extraParams) {
    Object.entries(extraParams).forEach(([k, v]) => params.set(k, v));
  }
  const formData = new FormData();
  formData.append('file', file, file.name);
  return request<Record<string, unknown>>(`/filehandler/upload?${params.toString()}`, {
    method: 'POST',
    body: formData,
  });
}

export async function request<T>(
  endpoint: string,
  options: RequestInit = {},
  retry = true
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;

  const isFormData = options.body instanceof FormData;
  const headers: Record<string, string> = {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(options.headers as Record<string, string>),
    ...buildAuthHeaders(),
  };

  const config: RequestInit = {
    ...options,
    headers,
  };

  const response = await fetch(url, config);

  if (response.status === 401 && retry) {
    if (BYPASS_AUTH) {
      throw createApiError({
        status: 401,
        statusText: 'Unauthorized',
        message: 'Request requires auth, but auth bypass is enabled.',
      });
    }
    const sessionProvider = getSessionProvider();
    if (sessionProvider === 'microsoft') {
      clearTokens();
      if (window.location.pathname !== '/login' && window.location.pathname !== '/auth/microsoft/callback') {
        window.location.href = '/login';
      }
      throw createApiError({
        status: 401,
        statusText: 'Unauthorized',
        message: 'Session expired. Please log in again.',
      });
    }

    const refreshed = await handleTokenRefresh();
    if (refreshed) {
      return request<T>(endpoint, options, false);
    }
    clearTokens();
    if (window.location.pathname !== '/login' && window.location.pathname !== '/auth/google/callback') {
      window.location.href = '/login';
    }
    throw createApiError({
      status: 401,
      statusText: 'Unauthorized',
      message: 'Session expired. Please log in again.',
    });
  }

  if (!response.ok) {
    let message: string | undefined;
    let detail: unknown;

    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      try {
        const json = await response.json();
        if (json && json.success === false && typeof json.message === 'string') {
          message = json.message;
          detail = { error_code: json.error_code ?? null, message: json.message };
        } else if (json.detail) {
          detail = json.detail;
          if (typeof json.detail === 'string') {
            message = json.detail;
          } else if (Array.isArray(json.detail)) {
            message = json.detail
              .map((e: { msg?: string; loc?: string[] }) => {
                const field = e.loc ? e.loc.filter(l => l !== 'body').join('.') : '';
                return field ? `${field}: ${e.msg}` : e.msg;
              })
              .filter(Boolean)
              .join('; ');
          } else if (typeof json.detail === 'object' && json.detail.failure_detail) {
            message = json.detail.failure_detail;
          } else {
            message = JSON.stringify(json.detail);
          }
        } else {
          message = JSON.stringify(json);
        }
      } catch {
        message = await response.text().catch(() => undefined);
      }
    } else {
      message = await response.text().catch(() => undefined);
    }

    throw createApiError({
      status: response.status,
      statusText: response.statusText,
      message,
      detail,
    });
  }

  if (response.status === 204 || response.status === 205) {
    return undefined as unknown as T;
  }

  const okContentType = (response.headers.get('content-type') || '').toLowerCase();
  const rawBody = await response.text().catch(() => '');
  if (!rawBody || !rawBody.trim()) {
    return undefined as unknown as T;
  }

  if (okContentType.includes('application/json')) {
    return JSON.parse(rawBody) as T;
  }

  return rawBody as unknown as T;
}