/**
 * Skeleton Component
 *
 * Animated placeholder components for loading states.
 * Provides a smooth shimmer animation effect.
 */

import type { HTMLAttributes } from 'react';

interface SkeletonProps extends HTMLAttributes<HTMLDivElement> {
  className?: string;
}

// Base skeleton with shimmer animation
export function Skeleton({ className = '', ...props }: SkeletonProps) {
  return (
    <div
      className={`
        animate-pulse bg-gradient-to-r from-muted via-accent/80 to-muted
        bg-[length:200%_100%] rounded-lg
        ${className}
      `}
      {...props}
    />
  );
}

// Text line skeleton
interface SkeletonTextProps extends SkeletonProps {
  lines?: number;
  lastLineWidth?: string;
}

export function SkeletonText({
  lines = 3,
  lastLineWidth = '75%',
  className = '',
  ...props
}: SkeletonTextProps) {
  return (
    <div className={`space-y-2 ${className}`} {...props}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          className="h-4"
          style={{
            width: i === lines - 1 ? lastLineWidth : '100%',
          }}
        />
      ))}
    </div>
  );
}

// Avatar skeleton
interface SkeletonAvatarProps extends SkeletonProps {
  size?: 'sm' | 'md' | 'lg';
}

const avatarSizes = {
  sm: 'w-8 h-8',
  md: 'w-10 h-10',
  lg: 'w-12 h-12',
};

export function SkeletonAvatar({
  size = 'md',
  className = '',
  ...props
}: SkeletonAvatarProps) {
  return (
    <Skeleton
      className={`rounded-full ${avatarSizes[size]} ${className}`}
      {...props}
    />
  );
}

// Card skeleton (matches ApplicationCard layout)
export function SkeletonCard({ className = '', ...props }: SkeletonProps) {
  return (
    <div
      className={`bg-card rounded-2xl shadow-sm p-4 space-y-3 ${className}`}
      {...props}
    >
      {/* Header with avatar and name */}
      <div className="flex items-center gap-3">
        <SkeletonAvatar size="md" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-3 w-24" />
        </div>
      </div>
      {/* Content */}
      <SkeletonText lines={2} />
      {/* Footer badges */}
      <div className="flex gap-2">
        <Skeleton className="h-6 w-16 rounded-full" />
        <Skeleton className="h-6 w-20 rounded-full" />
      </div>
    </div>
  );
}

// Table row skeleton
export function SkeletonTableRow({
  columns = 4,
  className = '',
  ...props
}: SkeletonProps & { columns?: number }) {
  return (
    <div
      className={`flex items-center gap-4 py-4 border-b border-border ${className}`}
      {...props}
    >
      {Array.from({ length: columns }).map((_, i) => (
        <Skeleton
          key={i}
          className="h-4 flex-1"
          style={{
            maxWidth: i === 0 ? '200px' : i === columns - 1 ? '80px' : '150px',
          }}
        />
      ))}
    </div>
  );
}

// Full page skeleton
export function SkeletonPage({ className = '', ...props }: SkeletonProps) {
  return (
    <div className={`space-y-6 p-6 ${className}`} {...props}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <Skeleton className="h-8 w-48" />
        <div className="flex gap-3">
          <Skeleton className="h-10 w-24 rounded-full" />
          <Skeleton className="h-10 w-32 rounded-full" />
        </div>
      </div>
      {/* Content grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    </div>
  );
}

// Kanban column skeleton
export function SkeletonKanbanColumn({ className = '', ...props }: SkeletonProps) {
  return (
    <div
      className={`bg-muted/50 rounded-xl p-4 min-w-[300px] ${className}`}
      {...props}
    >
      {/* Column header */}
      <div className="flex items-center justify-between mb-4">
        <Skeleton className="h-5 w-24" />
        <Skeleton className="h-5 w-8 rounded-full" />
      </div>
      {/* Cards */}
      <div className="space-y-3">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    </div>
  );
}

export default Skeleton;
