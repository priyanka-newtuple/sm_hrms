/**
 * AvatarStack Component
 *
 * Displays overlapping circular avatars with an optional +N overflow badge.
 * Used to show team interest (likes) on application cards.
 */

import { memo, useMemo } from 'react';
import Tooltip from './Tooltip';
import { getInitials, getAvatarColorClass } from '@/core/utils';

interface User {
  user_id: string;
  user_name: string;
  user_avatar_url?: string | null;
}

interface AvatarStackProps {
  /** List of users to display */
  users: User[];
  /** Maximum number of avatars to show before +N badge */
  maxAvatars?: number;
  /** Size variant: sm for cards, md for detail panels */
  size?: 'sm' | 'md';
  /** Additional CSS class */
  className?: string;
}

function AvatarStack({
  users,
  maxAvatars = 3,
  size = 'sm',
  className = '',
}: AvatarStackProps) {
  // Memoize size-based classes
  const sizeClasses = useMemo(() => {
    const sizes = {
      sm: {
        avatar: 'w-6 h-6 text-[10px]',
        overlap: '-ml-2',
        badge: 'w-6 h-6 text-[10px]',
      },
      md: {
        avatar: 'w-8 h-8 text-xs',
        overlap: '-ml-2.5',
        badge: 'w-8 h-8 text-xs',
      },
    };
    return sizes[size];
  }, [size]);

  if (!users || users.length === 0) {
    return null;
  }

  const visibleUsers = users.slice(0, maxAvatars);
  const overflowCount = users.length - maxAvatars;
  const overflowUsers = users.slice(maxAvatars);

  // Build tooltip content showing all user names
  const tooltipContent = (
    <div className="flex flex-col gap-0.5">
      {users.map((user) => (
        <span key={user.user_id}>{user.user_name}</span>
      ))}
    </div>
  );

  return (
    <Tooltip content={tooltipContent} position="top">
      <div className={`flex items-center ${className}`}>
        {visibleUsers.map((user, index) => (
          <div
            key={user.user_id}
            className={`
              ${sizeClasses.avatar}
              ${index > 0 ? sizeClasses.overlap : ''}
              rounded-full border-2 border-white
              flex items-center justify-center
              font-medium text-white
              overflow-hidden
              ${user.user_avatar_url ? '' : getAvatarColorClass(user.user_id)}
            `}
            style={{ zIndex: visibleUsers.length - index }}
          >
            {user.user_avatar_url ? (
              <img
                src={user.user_avatar_url}
                alt={user.user_name}
                className="w-full h-full object-cover"
              />
            ) : (
              getInitials(user.user_name)
            )}
          </div>
        ))}

        {/* Overflow badge */}
        {overflowCount > 0 && (
          <Tooltip
            content={
              <div className="flex flex-col gap-0.5">
                {overflowUsers.map((user) => (
                  <span key={user.user_id}>{user.user_name}</span>
                ))}
              </div>
            }
            position="top"
          >
            <div
              className={`
                ${sizeClasses.badge}
                ${sizeClasses.overlap}
                rounded-full border-2 border-white
                bg-accent text-muted-foreground
                flex items-center justify-center
                font-semibold
              `}
              style={{ zIndex: 0 }}
            >
              +{overflowCount}
            </div>
          </Tooltip>
        )}
      </div>
    </Tooltip>
  );
}

export default memo(AvatarStack);
