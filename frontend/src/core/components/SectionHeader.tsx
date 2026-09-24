import type { HTMLAttributes, ReactNode } from 'react';
import { cn } from '../../lib/utils';

interface SectionHeaderProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  title: ReactNode;
  description?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  meta?: ReactNode;
  iconClassName?: string;
}

export default function SectionHeader({
  title,
  description,
  icon,
  actions,
  meta,
  className,
  iconClassName,
  ...props
}: SectionHeaderProps) {
  return (
    <div
      className={cn(
        'flex flex-col gap-4 md:flex-row md:items-start md:justify-between',
        className,
      )}
      {...props}
    >
      <div className="flex items-start gap-3">
        {icon && (
          <div
            className={cn(
              'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary',
              iconClassName,
            )}
          >
            {icon}
          </div>
        )}
        <div>
          <h2 className="text-lg font-semibold text-foreground">{title}</h2>
          {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
          {meta && <div className="mt-2">{meta}</div>}
        </div>
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

export type { SectionHeaderProps };
