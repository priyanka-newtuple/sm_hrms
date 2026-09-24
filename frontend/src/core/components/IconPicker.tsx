/**
 * IconPicker Component
 *
 * Presentational grid for choosing a widget icon. The parent owns the selected
 * icon name; this component only renders the choices and emits the next name.
 * An empty selection (`''`) means "no icon". No business logic.
 */

import { Ban } from 'lucide-react';
import { cn } from '../../lib/utils';
import { WIDGET_ICON_NAMES, WIDGET_ICONS } from './widgetIcons';

interface IconPickerProps {
  value: string;
  onChange: (next: string) => void;
  label?: string;
}

export default function IconPicker({ value, onChange, label = 'Icon' }: IconPickerProps) {
  return (
    <div className="space-y-1.5">
      <span className="text-sm font-medium text-foreground">{label}</span>
      <div className="flex flex-wrap gap-1.5">
        <button
          type="button"
          aria-label="No icon"
          aria-pressed={value === ''}
          onClick={() => onChange('')}
          className={cn(
            'flex h-9 w-9 items-center justify-center rounded-lg border',
            value === ''
              ? 'border-cobalt bg-cobalt/10 text-cobalt'
              : 'border-border text-muted-foreground hover:bg-muted',
          )}
        >
          <Ban className="h-4 w-4" strokeWidth={1.5} />
        </button>
        {WIDGET_ICON_NAMES.map((name) => {
          const Icon = WIDGET_ICONS[name];
          const active = value === name;
          return (
            <button
              key={name}
              type="button"
              aria-label={name}
              aria-pressed={active}
              onClick={() => onChange(name)}
              className={cn(
                'flex h-9 w-9 items-center justify-center rounded-lg border',
                active
                  ? 'border-cobalt bg-cobalt/10 text-cobalt'
                  : 'border-border text-muted-foreground hover:bg-muted',
              )}
            >
              <Icon className="h-4 w-4" strokeWidth={1.5} />
            </button>
          );
        })}
      </div>
    </div>
  );
}

export type { IconPickerProps };
