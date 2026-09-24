/**
 * ViewToggle Component
 *
 * A button group for toggling between different view modes (e.g., Kanban/List).
 */

import type { ReactNode } from 'react';
import { Button } from '@/components/ui/button';

export type ViewMode = 'kanban' | 'list';

interface ViewToggleOption {
  value: ViewMode;
  label: string;
  icon: ReactNode;
}

interface ViewToggleProps {
  value: ViewMode;
  onChange: (value: ViewMode) => void;
  options: ViewToggleOption[];
  className?: string;
}

export default function ViewToggle({ value, onChange, options, className = '' }: ViewToggleProps) {
  return (
    <div className={`inline-flex rounded-lg border border-border bg-card p-1 ${className}`}>
      {options.map((option) => {
        const isActive = value === option.value;
        return (
          <Button
            key={option.value}
            variant={isActive ? 'primary' : 'ghost'}
            size="sm"
            onClick={() => onChange(option.value)}
            className="flex items-center gap-1.5"
          >
            {option.icon}
            <span>{option.label}</span>
          </Button>
        );
      })}
    </div>
  );
}
