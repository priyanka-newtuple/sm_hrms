import { Monitor, Moon, Sun } from 'lucide-react';

import { cn } from '@/lib/utils';
import { useThemeMode, type ThemePreference } from '@/core/theme';

const MODES: ReadonlyArray<{
  value: ThemePreference;
  label: string;
  icon: typeof Sun;
}> = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'System', icon: Monitor },
];

/** Three-way Light / Dark / System switch, rendered inside the account menu. */
export function ThemeModeToggle() {
  const { theme, setTheme } = useThemeMode();

  return (
    <div
      role="radiogroup"
      aria-label="Color theme"
      className="flex gap-0.5 rounded-lg bg-muted p-0.5"
    >
      {MODES.map(({ value, label, icon: Icon }) => {
        const active = theme === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => setTheme(value)}
            className={cn(
              'flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5',
              'text-[11px] font-medium transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40',
              active
                ? 'bg-card text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <Icon className="size-3.5" aria-hidden="true" />
            {label}
          </button>
        );
      })}
    </div>
  );
}
