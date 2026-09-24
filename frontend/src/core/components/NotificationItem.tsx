/**
 * NotificationItem Component
 *
 * Displays a single notification with action capabilities.
 */

import { formatDistanceToNow } from 'date-fns';
import { MessageSquare, ArrowRight, AlertTriangle, Bell, Trash2 } from 'lucide-react';
import type { Notification, NotificationType } from '../types';
import { Button } from '@/components/ui/button';
import { parseMentionText } from '@/core/utils/mentions';

interface NotificationItemProps {
  notification: Notification;
  onMarkAsRead?: (id: string) => void;
  onDelete?: (id: string) => void;
  onClick?: (notification: Notification) => void;
}

const TYPE_ICONS: Record<NotificationType, typeof Bell> = {
  mention: MessageSquare,
  assignment: ArrowRight,
  transition: ArrowRight,
  sla_warning: AlertTriangle,
  system: Bell,
};

const TYPE_COLORS: Record<NotificationType, string> = {
  mention: 'bg-primary/10 text-primary',
  assignment: 'bg-emerald/10 text-emerald',
  transition: 'bg-violet/10 text-violet',
  sla_warning: 'bg-amber/10 text-amber',
  system: 'bg-muted text-muted-foreground',
};

export default function NotificationItem({
  notification,
  onMarkAsRead,
  onDelete,
  onClick,
}: NotificationItemProps) {
  const Icon = TYPE_ICONS[notification.notification_type as NotificationType] || Bell;
  const colorClass = TYPE_COLORS[notification.notification_type as NotificationType] || TYPE_COLORS.system;

  const handleClick = () => {
    if (!notification.is_read && onMarkAsRead) {
      onMarkAsRead(notification.id);
    }
    onClick?.(notification);
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    onDelete?.(notification.id);
  };

  const timeAgo = formatDistanceToNow(new Date(notification.created_at), { addSuffix: true });
  const notificationBody = notification.body ? parseMentionText(notification.body).text : null;

  return (
    <div
      onClick={handleClick}
      className={`group relative flex gap-3 p-3 rounded-xl cursor-pointer transition-all duration-200
        ${notification.is_read
          ? 'bg-card hover:bg-accent/40'
          : 'bg-primary/5 hover:bg-primary/10'
        }`}
    >
      {/* Unread indicator */}
      {!notification.is_read && (
        <div className="absolute left-1 top-1/2 h-1.5 w-1.5 -translate-y-1/2 rounded-full bg-primary" />
      )}

      {/* Icon */}
      <div className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center ${colorClass}`}>
        <Icon className="w-4 h-4" />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <p className={`text-sm ${notification.is_read ? 'text-foreground/85' : 'font-medium text-foreground'}`}>
          {notification.title}
        </p>
        {notificationBody && (
          <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
            {notificationBody}
          </p>
        )}
        <div className="flex items-center gap-2 mt-1">
          {notification.actor_name && (
            <span className="text-xs text-muted-foreground">
              by {notification.actor_name}
            </span>
          )}
          <span className="text-xs text-muted-foreground">{timeAgo}</span>
        </div>
      </div>

      {/* Delete button */}
      {onDelete && (
        <Button
          variant="ghost"
          onClick={handleDelete}
          className="flex-shrink-0 rounded-lg p-1.5 text-muted-foreground opacity-0 transition-all group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </Button>
      )}
    </div>
  );
}
