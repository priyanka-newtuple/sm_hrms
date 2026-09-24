import type { HTMLAttributes, ReactNode } from 'react';
import { cn } from '../../lib/utils';

type PanelPadding = 'none' | 'sm' | 'md' | 'lg';
type PanelRadius = 'xl' | '2xl';
type PanelTone = 'default' | 'muted';

interface PanelProps extends HTMLAttributes<HTMLDivElement> {
  padding?: PanelPadding;
  radius?: PanelRadius;
  tone?: PanelTone;
  bordered?: boolean;
  shadow?: boolean;
  overflowHidden?: boolean;
  children: ReactNode;
}

interface PanelHeaderProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  title?: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  children?: ReactNode;
}

interface PanelBodyProps extends HTMLAttributes<HTMLDivElement> {
  padding?: PanelPadding;
  children: ReactNode;
}

interface PanelFooterProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

const paddingStyles: Record<PanelPadding, string> = {
  none: 'p-0',
  sm: 'p-3',
  md: 'p-4',
  lg: 'p-6',
};

const radiusStyles: Record<PanelRadius, string> = {
  xl: 'rounded-xl',
  '2xl': 'rounded-2xl',
};

const toneStyles: Record<PanelTone, string> = {
  default: 'bg-card text-card-foreground',
  muted: 'bg-muted text-foreground',
};

export default function Panel({
  padding = 'md',
  radius = 'xl',
  tone = 'default',
  bordered = true,
  shadow = false,
  overflowHidden = false,
  className,
  children,
  ...props
}: PanelProps) {
  return (
    <div
      className={cn(
        toneStyles[tone],
        radiusStyles[radius],
        bordered && 'border border-border',
        shadow && 'shadow-sm',
        overflowHidden && 'overflow-hidden',
        paddingStyles[padding],
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function PanelHeader({
  title,
  description,
  action,
  children,
  className,
  ...props
}: PanelHeaderProps) {
  return (
    <div
      className={cn(
        'flex items-start justify-between gap-4 border-b border-border px-4 py-3',
        className,
      )}
      {...props}
    >
      <div className="min-w-0">
        {title && <h3 className="font-semibold text-card-foreground">{title}</h3>}
        {description && <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>}
        {children}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export function PanelBody({
  padding = 'md',
  className,
  children,
  ...props
}: PanelBodyProps) {
  return (
    <div className={cn(paddingStyles[padding], className)} {...props}>
      {children}
    </div>
  );
}

export function PanelFooter({
  className,
  children,
  ...props
}: PanelFooterProps) {
  return (
    <div
      className={cn(
        'flex items-center justify-end gap-3 border-t border-border bg-muted/60 px-4 py-3',
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export type {
  PanelBodyProps,
  PanelFooterProps,
  PanelHeaderProps,
  PanelPadding,
  PanelProps,
  PanelRadius,
  PanelTone,
};
