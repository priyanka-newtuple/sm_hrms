import type { User, UserRole, UserStatus, UserStatsResponse } from '../../types';
import { request } from './client';

/** The largest page `/users` will serve (`le=200` on the endpoint). */
const USERS_PAGE_SIZE = 200;

/** Stop requesting after this many pages, so a misbehaving endpoint cannot loop forever. */
const USERS_MAX_PAGES = 10;

export const users = {
  /**
   * Every user in the organization, following pagination.
   *
   * `/users` serves 50 by default and 200 at most, so a single request silently
   * truncates a larger organization — anyone past the first page would be
   * missing from the assignee pickers that call this.
   */
  list: async (status?: UserStatus): Promise<User[]> => {
    const collected: User[] = [];
    for (let page = 0; page < USERS_MAX_PAGES; page += 1) {
      const params = new URLSearchParams({
        limit: String(USERS_PAGE_SIZE),
        offset: String(page * USERS_PAGE_SIZE),
      });
      if (status) params.set('status', status);
      const batch = await request<User[]>(`/users?${params.toString()}`);
      collected.push(...batch);
      if (batch.length < USERS_PAGE_SIZE) return collected;
    }
    console.warn(
      `users.list stopped at ${USERS_MAX_PAGES * USERS_PAGE_SIZE} users; ` +
        'this organization needs a searchable picker rather than a dropdown.',
    );
    return collected;
  },

  listPending: () => request<User[]>('/users/pending'),

  get: (userId: string) => request<User>(`/users/${userId}`),

  approve: (userId: string) =>
    request<User>(`/users/${userId}/approve`, { method: 'POST' }),

  reject: (userId: string) =>
    request<User>(`/users/${userId}/reject`, { method: 'POST' }),

  suspend: (userId: string) =>
    request<User>(`/users/${userId}/suspend`, { method: 'POST' }),

  reactivate: (userId: string) =>
    request<User>(`/users/${userId}/reactivate`, { method: 'POST' }),

  updateRole: (userId: string, role: UserRole) =>
    request<User>(`/users/${userId}/role`, {
      method: 'PUT',
      body: JSON.stringify({ role }),
    }),

  getStats: () => request<UserStatsResponse>('/users/stats/summary'),
};
