/**
 * Notifications Hook
 *
 * Provides notifications state with polling for real-time updates.
 * Uses 30-second polling interval to check for new notifications.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { notifications as notificationsApi } from '../services/api';
import type { Notification, NotificationListResponse } from '../types';

const POLLING_INTERVAL = 30000; // 30 seconds

interface UseNotificationsOptions {
  enabled?: boolean;
  pollingInterval?: number;
}

interface UseNotificationsResult {
  notifications: Notification[];
  unreadCount: number;
  total: number;
  loading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
  markAsRead: (notificationId: string) => Promise<void>;
  markAllAsRead: () => Promise<void>;
  deleteNotification: (notificationId: string) => Promise<void>;
}

export function useNotifications(
  options: UseNotificationsOptions = {}
): UseNotificationsResult {
  const { enabled = true, pollingInterval = POLLING_INTERVAL } = options;

  const [data, setData] = useState<NotificationListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  // Keep track of whether component is mounted
  const mountedRef = useRef(true);

  const fetchNotifications = useCallback(async () => {
    if (!enabled) return;

    try {
      const result = await notificationsApi.list({ limit: 50 });
      if (mountedRef.current) {
        setData(result);
        setError(null);
      }
    } catch (e) {
      if (mountedRef.current) {
        setError(e instanceof Error ? e : new Error(String(e)));
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, [enabled]);

  // Initial fetch and polling setup
  useEffect(() => {
    mountedRef.current = true;

    if (enabled) {
      fetchNotifications();

      // Set up polling
      const intervalId = setInterval(fetchNotifications, pollingInterval);

      return () => {
        mountedRef.current = false;
        clearInterval(intervalId);
      };
    }

    return () => {
      mountedRef.current = false;
    };
  }, [enabled, pollingInterval, fetchNotifications]);

  const markAsRead = useCallback(async (notificationId: string) => {
    try {
      const updated = await notificationsApi.markAsRead(notificationId);
      setData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          notifications: prev.notifications.map((n) =>
            n.id === notificationId ? updated : n
          ),
          unread_count: Math.max(0, prev.unread_count - 1),
        };
      });
    } catch (e) {
      throw e instanceof Error ? e : new Error(String(e));
    }
  }, []);

  const markAllAsRead = useCallback(async () => {
    try {
      await notificationsApi.markAllAsRead();
      setData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          notifications: prev.notifications.map((n) => ({
            ...n,
            is_read: true,
            read_at: new Date().toISOString(),
          })),
          unread_count: 0,
        };
      });
    } catch (e) {
      throw e instanceof Error ? e : new Error(String(e));
    }
  }, []);

  const deleteNotification = useCallback(async (notificationId: string) => {
    try {
      await notificationsApi.delete(notificationId);
      setData((prev) => {
        if (!prev) return prev;
        const notification = prev.notifications.find((n) => n.id === notificationId);
        const wasUnread = notification && !notification.is_read;
        return {
          ...prev,
          notifications: prev.notifications.filter((n) => n.id !== notificationId),
          total: prev.total - 1,
          unread_count: wasUnread
            ? Math.max(0, prev.unread_count - 1)
            : prev.unread_count,
        };
      });
    } catch (e) {
      throw e instanceof Error ? e : new Error(String(e));
    }
  }, []);

  return {
    notifications: data?.notifications ?? [],
    unreadCount: data?.unread_count ?? 0,
    total: data?.total ?? 0,
    loading,
    error,
    refetch: fetchNotifications,
    markAsRead,
    markAllAsRead,
    deleteNotification,
  };
}
