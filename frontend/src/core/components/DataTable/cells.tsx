import type { MouseEvent, ReactNode } from 'react';

import { cn } from '@/lib/utils';

/**
 * Reusable cell renderers shared by every data table. Import these rather than
 * restyling badges/links/avatars per table — they carry the platform look and
 * the light/dark pairs.
 */

const TAG_TONES = ['amber', 'green', 'blue', 'purple', 'pink', 'teal'] as const;
export type TagTone = (typeof TAG_TONES)[number] | 'gray';

const tagClass: Record<TagTone, string> = {
  amber: 'bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-300',
  green: 'bg-green-100 text-green-800 dark:bg-green-400/15 dark:text-green-300',
  blue: 'bg-blue-100 text-blue-800 dark:bg-blue-400/15 dark:text-blue-300',
  purple: 'bg-purple-100 text-purple-800 dark:bg-purple-400/15 dark:text-purple-300',
  pink: 'bg-pink-100 text-pink-800 dark:bg-pink-400/15 dark:text-pink-300',
  teal: 'bg-teal-100 text-teal-800 dark:bg-teal-400/15 dark:text-teal-300',
  gray: 'bg-muted text-foreground/70',
};

/** Stable tone per value, so a given tag keeps its colour across renders and tables. */
function toneFor(value: string): TagTone {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) hash = (hash * 31 + value.charCodeAt(i)) >>> 0;
  return TAG_TONES[hash % TAG_TONES.length];
}

export function TagCell({
  values,
  toneOf,
}: {
  values: string[];
  /** Override the automatic colour assignment. */
  toneOf?: (value: string) => TagTone;
}) {
  if (values.length === 0) return <span className="text-muted-foreground/50">—</span>;
  return (
    <div className="flex items-center gap-1 overflow-hidden">
      {values.map((value) => (
        <span
          key={value}
          className={cn(
            'shrink-0 rounded px-1.5 py-0.5 text-[12px] font-medium',
            tagClass[toneOf?.(value) ?? toneFor(value)],
          )}
        >
          {value}
        </span>
      ))}
    </div>
  );
}

export type StatusTone = 'neutral' | 'success' | 'warning' | 'danger' | 'info';

const statusDot: Record<StatusTone, string> = {
  neutral: 'bg-muted-foreground/40',
  success: 'bg-emerald-500',
  warning: 'bg-amber-500',
  danger: 'bg-rose-500',
  info: 'bg-sky-500',
};

/** Status as dot/icon + label — never colour alone, so it reads without colour vision. */
export function StatusCell({
  label,
  tone = 'neutral',
  muted,
  icon,
}: {
  label: string;
  tone?: StatusTone;
  muted?: boolean;
  icon?: ReactNode;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-2 text-[13px]',
        muted ? 'text-muted-foreground/70' : 'text-foreground/85',
      )}
    >
      {icon ?? <span className={cn('size-2 shrink-0 rounded-full', statusDot[tone])} />}
      {label}
    </span>
  );
}

export function LinkCell({
  href,
  children,
  onClick,
}: {
  href?: string;
  children: ReactNode;
  onClick?: (event: MouseEvent<HTMLAnchorElement>) => void;
}) {
  return (
    <a
      href={href}
      // Row click shouldn't fire when the user meant the link.
      onClick={(event) => {
        event.stopPropagation();
        onClick?.(event);
      }}
      className="text-[13px] text-sky-600 underline decoration-border underline-offset-2 hover:decoration-sky-500 dark:text-sky-400"
    >
      {children}
    </a>
  );
}

export function AvatarCell({
  name,
  initials,
  color,
  logoUrl,
  subtitle,
}: {
  name: string;
  initials?: string;
  color?: string;
  logoUrl?: string;
  subtitle?: string;
}) {
  return (
    <div className="flex items-center gap-2.5">
      {logoUrl ? (
        <img src={logoUrl} alt="" className="size-5 shrink-0 rounded-[6px] object-cover" />
      ) : (
        <span
          className="flex size-5 shrink-0 items-center justify-center rounded-[6px] text-[10px] font-semibold text-white"
          style={{ background: color ?? 'var(--primary)' }}
        >
          {initials ?? name.slice(0, 1).toUpperCase()}
        </span>
      )}
      <span className="flex min-w-0 flex-col leading-tight">
        <span className="truncate font-medium text-foreground">{name}</span>
        {subtitle && <span className="truncate text-[12px] text-muted-foreground">{subtitle}</span>}
      </span>
    </div>
  );
}

export function DateCell({ children }: { children: ReactNode }) {
  if (children == null || children === '') return <span className="text-muted-foreground/50">—</span>;
  return <span className="text-[13px] tabular-nums text-muted-foreground">{children}</span>;
}

export function NumberCell({ value }: { value: number | null | undefined }) {
  return (
    <span className="block text-right text-[13px] tabular-nums text-foreground/80">
      {value == null ? '—' : value.toLocaleString()}
    </span>
  );
}
