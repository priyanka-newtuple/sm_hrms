/**
 * Badge Component
 *
 * Shared badge styles aligned with the app token system.
 */

import { Sparkles } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '../../lib/utils';

type BadgeVariant = 'default' | 'success' | 'warning' | 'error' | 'cobalt' | 'ai' | 'gradient';
type BadgeSize = 'sm' | 'md';

interface BadgeProps {
  children: ReactNode;
  variant?: BadgeVariant;
  size?: BadgeSize;
  icon?: ReactNode;
  pulse?: boolean;
  className?: string;
}

const variantStyles: Record<BadgeVariant, string> = {
  default: 'border border-border bg-muted text-muted-foreground',
  success: 'border border-emerald/20 bg-emerald/10 text-emerald',
  warning: 'border border-amber/20 bg-amber/10 text-amber',
  error: 'border border-rose/20 bg-rose/10 text-rose',
  cobalt: 'border border-cobalt/20 bg-cobalt/10 text-cobalt',
  ai: 'border border-violet/20 bg-[linear-gradient(135deg,rgba(0,71,171,0.1)_0%,rgba(0,184,217,0.1)_50%,rgba(139,92,246,0.1)_100%)] text-violet',
  gradient: 'border border-transparent bg-[linear-gradient(135deg,#0047AB_0%,#00B8D9_50%,#8B5CF6_100%)] text-white shadow-sm',
};

const sizeStyles: Record<BadgeSize, string> = {
  sm: 'px-2 py-0.5 text-[10px] gap-1',
  md: 'px-2.5 py-1 text-xs gap-1.5',
};

export default function Badge({
  children,
  variant = 'default',
  size = 'sm',
  icon,
  pulse = false,
  className = '',
}: BadgeProps) {
  const showAiIcon = variant === 'ai' && !icon;

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full font-semibold transition-colors duration-200',
        variantStyles[variant],
        sizeStyles[size],
        pulse && 'animate-pulse',
        className,
      )}
    >
      {showAiIcon && <Sparkles className="w-3 h-3" />}
      {icon && <span className="flex-shrink-0">{icon}</span>}
      {children}
    </span>
  );
}

export type { BadgeProps, BadgeVariant, BadgeSize };
