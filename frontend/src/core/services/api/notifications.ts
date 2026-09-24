import type {
  Notification,
  NotificationListResponse,
  UnreadCountResponse,
  MarkAllReadResponse,
} from '../../types';
import { request } from './client';

export const notifications = {
  list: (params?: { is_read?: boolean; limit?: number; offset?: number }) => {
    const searchParams = new URLSearchParams();
    if (params?.is_read !== undefined) searchParams.set('is_read', params.is_read.toString());
    if (params?.limit) searchParams.set('limit', params.limit.toString());
    if (params?.offset) searchParams.set('offset', params.offset.toString());
    const query = searchParams.toString();
    return request<NotificationListResponse>(`/notifications${query ? `?${query}` : ''}`);
  },

  getUnreadCount: () =>
    request<UnreadCountResponse>('/notifications/unread-count'),

  markAsRead: (notificationId: string) =>
    request<Notification>(`/notifications/${notificationId}/read`, {
      method: 'POST',
    }),

  markAllAsRead: () =>
    request<MarkAllReadResponse>('/notifications/mark-all-read', {
      method: 'POST',
    }),

  delete: (notificationId: string) =>
    request<void>(`/notifications/${notificationId}`, {
      method: 'DELETE',
    }),
};
