/**
 * Card Component
 *
 * A modern card component with elevation levels and hover effects.
 * Uses shadows instead of borders for a cleaner, elevated look.
 */

import { forwardRef, type HTMLAttributes, type ReactNode } from 'react';
import { cn } from '../../lib/utils';

type CardElevation = 'none' | 'sm' | 'md' | 'lg';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  elevation?: CardElevation;
  hover?: boolean;
  selected?: boolean;
  padding?: 'none' | 'sm' | 'md' | 'lg';
  children: ReactNode;
}

const elevationStyles: Record<CardElevation, string> = {
  none: 'shadow-none',
  sm: 'shadow-sm',
  md: 'shadow-md',
  lg: 'shadow-lg',
};

const hoverElevationStyles: Record<CardElevation, string> = {
  none: 'hover:shadow-sm',
  sm: 'hover:shadow-md',
  md: 'hover:shadow-lg',
  lg: 'hover:shadow-xl',
};

const paddingStyles: Record<'none' | 'sm' | 'md' | 'lg', string> = {
  none: 'p-0',
  sm: 'p-3',
  md: 'p-4',
  lg: 'p-6',
};

const Card = forwardRef<HTMLDivElement, CardProps>(
  (
    {
      elevation = 'sm',
      hover = false,
      selected = false,
      padding = 'md',
      children,
      className = '',
      ...props
    },
    ref
  ) => {
    return (
      <div
        ref={ref}
        className={cn(
          'rounded-2xl border border-border bg-card text-card-foreground transition-all duration-200 ease-out',
          elevationStyles[elevation],
          hover && `${hoverElevationStyles[elevation]} hover:-translate-y-0.5 cursor-pointer`,
          selected && 'ring-2 ring-ring/30',
          paddingStyles[padding],
          className,
        )}
        {...props}
      >
        {children}
      </div>
    );
  }
);

Card.displayName = 'Card';

// Card Header sub-component
interface CardHeaderProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  action?: ReactNode;
}

function CardHeader({ children, action, className = '', ...props }: CardHeaderProps) {
  return (
    <div
      className={cn('flex items-center justify-between border-b border-border pb-4', className)}
      {...props}
    >
      <div className="font-semibold text-card-foreground">{children}</div>
      {action && <div>{action}</div>}
    </div>
  );
}

// Card Body sub-component
interface CardBodyProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

function CardBody({ children, className = '', ...props }: CardBodyProps) {
  return (
    <div className={cn('py-4', className)} {...props}>
      {children}
    </div>
  );
}

// Card Footer sub-component
interface CardFooterProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

function CardFooter({ children, className = '', ...props }: CardFooterProps) {
  return (
    <div
      className={cn('flex items-center justify-end gap-3 border-t border-border pt-4', className)}
      {...props}
    >
      {children}
    </div>
  );
}

export default Card;
export { CardHeader, CardBody, CardFooter };
export type { CardProps, CardElevation };
