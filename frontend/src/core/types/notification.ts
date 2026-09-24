/**
 * Notification Types
 *
 * Types for the in-app notification system.
 */

// Notification types
export type NotificationType =
  | 'mention'
  | 'assignment'
  | 'transition'
  | 'sla_warning'
  | 'system';

// Notification from API
export interface Notification {
  id: string;
  organization_id: string;
  recipient_id: string;
  notification_type: NotificationType;
  source_type: string | null;
  source_id: string | null;
  entity_id: string;
  entity_type: string;
  actor_id: string | null;
  actor_name: string | null;
  title: string;
  body: string | null;
  link: string | null;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}

// List notifications response
export interface NotificationListResponse {
  notifications: Notification[];
  total: number;
  unread_count: number;
}

// Unread count response
export interface UnreadCountResponse {
  count: number;
}

// Mark all read response
export interface MarkAllReadResponse {
  updated: number;
}
