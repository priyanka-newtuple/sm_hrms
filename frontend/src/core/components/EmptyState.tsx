import type { HTMLAttributes, ReactNode } from 'react';
import { cn } from '../../lib/utils';

type EmptyStateSurface = 'subtle' | 'panel' | 'plain';

interface EmptyStateProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  title?: ReactNode;
  description?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
  surface?: EmptyStateSurface;
  children?: ReactNode;
}

const surfaceStyles: Record<EmptyStateSurface, string> = {
  subtle: 'rounded-xl bg-muted/60 py-12',
  panel: 'rounded-xl border border-border bg-card p-8',
  plain: 'py-8',
};

export default function EmptyState({
  title,
  description,
  icon,
  action,
  surface = 'subtle',
  children,
  className,
  ...props
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'text-center',
        surfaceStyles[surface],
        className,
      )}
      {...props}
    >
      {icon && <div className="mx-auto mb-4 flex w-fit items-center justify-center">{icon}</div>}
      {title && <h4 className="text-lg font-medium text-card-foreground">{title}</h4>}
      {description && (
        <p className={cn('text-sm text-muted-foreground', title ? 'mt-2' : 'mt-0')}>{description}</p>
      )}
      {children && <div className="mt-4">{children}</div>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

export type { EmptyStateProps, EmptyStateSurface };
