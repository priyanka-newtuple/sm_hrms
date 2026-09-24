import { request } from './client';

export const organizations = {
  list: (status?: string) => {
    const params = status ? `?status=${status}` : '';
    return request<{ items: Array<{
      id: string;
      name: string;
      slug: string;
      domain: string | null;
      settings: Record<string, unknown>;
      status: string;
      logo_url: string | null;
      requested_by_user_id: string | null;
      created_at: string;
      updated_at: string;
    }>; total: number }>(`/organizations${params}`);
  },

  listPending: () =>
    request<{ items: Array<{
      id: string;
      name: string;
      slug: string;
      domain: string | null;
      settings: Record<string, unknown>;
      status: string;
      logo_url: string | null;
      requested_by_user_id: string | null;
      requester_email: string | null;
      requester_name: string | null;
      created_at: string;
      updated_at: string;
    }>; total: number }>('/organizations/pending'),

  get: (orgId: string) => request<{
    id: string;
    name: string;
    slug: string;
    domain: string | null;
    settings: Record<string, unknown>;
    status: string;
    logo_url: string | null;
    created_at: string;
    updated_at: string;
  }>(`/organizations/${orgId}`),

  getCurrent: () => request<{
    id: string;
    name: string;
    slug: string;
    domain: string | null;
    settings: Record<string, unknown>;
    status: string;
    logo_url: string | null;
    created_at: string;
    updated_at: string;
  }>('/organizations/current'),

  update: (orgId: string, data: { name?: string; domain?: string | null; settings?: Record<string, unknown>; logo_url?: string | null }) =>
    request<{
      id: string;
      name: string;
      slug: string;
      domain: string | null;
      settings: Record<string, unknown>;
      status: string;
      logo_url: string | null;
      created_at: string;
      updated_at: string;
    }>(`/organizations/${orgId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  /**
   * Update branding (theme settings and/or logo) for the caller's own
   * organization. Allowed for org admins/owners, not just super admins; the
   * target org is derived server-side from the authenticated actor.
   */
  updateBranding: (data: { settings?: Record<string, unknown>; logo_url?: string | null }) =>
    request<{
      id: string;
      name: string;
      slug: string;
      domain: string | null;
      settings: Record<string, unknown>;
      status: string;
      logo_url: string | null;
      created_at: string;
      updated_at: string;
    }>(`/organizations/current/branding`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  renameCurrent: (name: string) =>
    request<{
      id: string;
      name: string;
      slug: string;
      domain: string | null;
      settings: Record<string, unknown>;
      status: string;
      logo_url: string | null;
      created_at: string;
      updated_at: string;
    }>('/organizations/current/name', {
      method: 'PUT',
      body: JSON.stringify({ name }),
    }),

  approve: (orgId: string) =>
    request<{ id: string; name: string; status: string }>(`/organizations/${orgId}/approve`, { method: 'POST' }),

  reject: (orgId: string) =>
    request<{ id: string; name: string; status: string }>(`/organizations/${orgId}/reject`, { method: 'POST' }),

  delete: (orgId: string) =>
    request<void>(`/organizations/${orgId}`, { method: 'DELETE' }),

  listUsers: (orgId: string, status?: string) => {
    const params = status ? `?status=${status}` : '';
    return request<{ items: Array<{
      id: string;
      email: string;
      full_name: string;
      avatar_url: string | null;
      role: string;
      status: string;
      auth_type: string;
      is_active: boolean;
      organization_id: string | null;
      last_login_at: string | null;
      created_at: string;
      updated_at: string | null;
    }>; total: number }>(`/organizations/${orgId}/users${params}`);
  },

  createUser: (orgId: string, data: { email: string; full_name: string; role?: string; status?: string }) =>
    request<{
      id: string;
      email: string;
      full_name: string;
      role: string;
      status: string;
      auth_type: string;
      is_active: boolean;
      organization_id: string | null;
      created_at: string;
    }>(`/organizations/${orgId}/users`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  deleteUser: (orgId: string, userId: string) =>
    request<void>(`/organizations/${orgId}/users/${userId}`, { method: 'DELETE' }),

  create: (data: { name: string; slug?: string }) =>
    request<{
      id: string;
      name: string;
      slug: string;
      domain: string | null;
      settings: Record<string, unknown>;
      status: string;
      logo_url: string | null;
      created_at: string;
      updated_at: string;
    }>('/organizations', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};
