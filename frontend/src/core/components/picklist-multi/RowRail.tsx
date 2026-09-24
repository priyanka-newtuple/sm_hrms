/** Step 3's left rail: one entry per row, with its item count. */

import { cn } from '@/lib/utils';
import type { Row } from './rows';

type RowRailProps = {
  rows: Row[];
  activeDropdown: string;
  onActivate: (dropdown: string) => void;
};

export default function RowRail({ rows, activeDropdown, onActivate }: RowRailProps) {
  return (
    <div className="flex w-[240px] shrink-0 flex-col overflow-y-auto border-r border-border p-2 max-[720px]:w-full max-[720px]:max-h-[220px] max-[720px]:border-r-0 max-[720px]:border-b">
      {rows.map((row) => {
        const isActive = row.dropdown === activeDropdown;
        return (
          <button
            key={row.dropdown}
            type="button"
            aria-current={isActive}
            onClick={() => onActivate(row.dropdown)}
            className={cn(
              'mb-0.5 flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-colors',
              isActive ? 'bg-cobalt text-primary-foreground' : 'text-foreground hover:bg-muted'
            )}
          >
            <span className="flex-1 truncate">{row.dropdown}</span>
            {row.toggles.length > 0 ? (
              <span
                className={cn(
                  'flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-xs font-semibold',
                  isActive ? 'bg-primary-foreground text-cobalt' : 'bg-cobalt text-primary-foreground'
                )}
              >
                {row.toggles.length}
              </span>
            ) : (
              <span
                className={cn(
                  'h-1.5 w-1.5 rounded-full',
                  isActive ? 'bg-primary-foreground/50' : 'bg-muted-foreground/40'
                )}
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
