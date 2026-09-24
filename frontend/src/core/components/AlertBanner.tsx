import type { HTMLAttributes, ReactNode } from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, Info } from 'lucide-react';
import { cn } from '../../lib/utils';

type AlertBannerTone = 'error' | 'warning' | 'info' | 'success';
type AlertBannerSize = 'sm' | 'md';

interface AlertBannerProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  tone?: AlertBannerTone;
  size?: AlertBannerSize;
  title?: ReactNode;
  actions?: ReactNode;
  icon?: ReactNode;
  children: ReactNode;
}

const toneStyles: Record<
  AlertBannerTone,
  {
    container: string;
    icon: string;
    title: string;
    body: string;
    defaultIcon: typeof AlertCircle;
  }
> = {
  error: {
    container: 'border-red-200 bg-red-50',
    icon: 'text-red-500',
    title: 'text-red-800',
    body: 'text-red-600',
    defaultIcon: AlertCircle,
  },
  warning: {
    container: 'border-amber-200 bg-amber-50',
    icon: 'text-amber-600',
    title: 'text-amber-800',
    body: 'text-amber-700',
    defaultIcon: AlertTriangle,
  },
  info: {
    container: 'border-primary/20 bg-primary/10',
    icon: 'text-primary',
    title: 'text-primary',
    body: 'text-foreground',
    defaultIcon: Info,
  },
  success: {
    container: 'border-emerald-200 bg-emerald-50',
    icon: 'text-emerald-500',
    title: 'text-emerald-800',
    body: 'text-emerald-700',
    defaultIcon: CheckCircle2,
  },
};

const sizeStyles: Record<AlertBannerSize, string> = {
  sm: 'gap-2 p-3',
  md: 'gap-3 p-4',
};

export default function AlertBanner({
  tone = 'info',
  size = 'md',
  title,
  actions,
  icon,
  children,
  className,
  ...props
}: AlertBannerProps) {
  const styles = toneStyles[tone];
  const DefaultIcon = styles.defaultIcon;

  return (
    <div
      className={cn(
        'rounded-lg border',
        styles.container,
        className,
      )}
      {...props}
    >
      <div className={cn('flex items-start', sizeStyles[size])}>
        {icon !== null && (
          <div className={cn('mt-0.5 shrink-0', styles.icon)}>
            {icon ?? <DefaultIcon className={size === 'sm' ? 'h-4 w-4' : 'h-5 w-5'} />}
          </div>
        )}
        <div className="min-w-0 flex-1">
          {title && <p className={cn('font-medium', styles.title)}>{title}</p>}
          <div className={cn('text-sm', styles.body, title && 'mt-1')}>{children}</div>
        </div>
        {actions && <div className="shrink-0">{actions}</div>}
      </div>
    </div>
  );
}

export type { AlertBannerProps, AlertBannerSize, AlertBannerTone };
