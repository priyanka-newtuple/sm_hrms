import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

type SegOption<T extends string> = { value: T; label: ReactNode; title?: string };

type Props<T extends string> = {
  options: readonly SegOption<T>[];
  value: T;
  onChange: (value: T) => void;
  size?: 'sm' | 'md';
  fill?: boolean;
  className?: string;
};

/** Small pill segmented control (a styled radiogroup). Shared across the app wherever a fixed, small set of exclusive options needs picking. */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  size = 'md',
  fill,
  className,
}: Props<T>) {
  return (
    <div
      role="radiogroup"
      className={cn(
        'rounded-lg border border-border bg-muted/50 p-0.5',
        fill ? 'flex w-full' : 'inline-flex',
        className,
      )}
    >
      {options.map((option) => {
        const isActive = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={isActive}
            title={option.title}
            onClick={() => onChange(option.value)}
            className={cn(
              'rounded-md font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cobalt',
              fill && 'flex-1',
              size === 'sm' ? 'px-2 py-1 text-xs' : 'px-2.5 py-1.5 text-sm',
              isActive ? 'bg-card text-cobalt shadow-sm' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
