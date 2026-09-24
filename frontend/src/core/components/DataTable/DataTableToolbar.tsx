import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

/** Slot row above a data table — filters and search on the left, actions on the right. */
export function DataTableToolbar({
  left,
  right,
  className,
}: {
  left?: ReactNode;
  right?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'flex shrink-0 items-center gap-2 border-b border-border/60 bg-background px-3 py-2',
        className,
      )}
    >
      {left}
      {right && <div className="ml-auto flex items-center gap-2">{right}</div>}
    </div>
  );
}
