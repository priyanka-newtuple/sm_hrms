/** One item in step 3's grid, on or off for the active row. */

import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';

type ItemCellProps = {
  label: string;
  isOn: boolean;
  disabled: boolean;
  onClick: () => void;
};

export default function ItemCell({ label, isOn, disabled, onClick }: ItemCellProps) {
  return (
    <button
      type="button"
      aria-pressed={isOn}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'flex items-start gap-2 rounded-lg border px-2.5 py-2 text-left text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-60',
        isOn ? 'border-cobalt bg-cobalt/5' : 'border-border bg-card'
      )}
    >
      <span
        className={cn(
          'mt-px flex h-[17px] w-[17px] shrink-0 items-center justify-center rounded border text-primary-foreground',
          isOn ? 'border-cobalt bg-cobalt' : 'border-border bg-card'
        )}
      >
        {isOn && <Check size={11} />}
      </span>
      <span className={isOn ? 'font-medium text-foreground' : 'text-foreground'}>{label}</span>
    </button>
  );
}
