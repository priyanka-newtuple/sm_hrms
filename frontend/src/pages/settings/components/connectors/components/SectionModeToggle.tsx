import { Braces, List } from 'lucide-react';

export type SectionEditMode = 'rows' | 'json';

interface SectionModeToggleProps {
  mode: SectionEditMode;
  onChange: (mode: SectionEditMode) => void;
  /** Modes the current content cannot survive, with the reason to show on hover. */
  disabled?: Partial<Record<SectionEditMode, string>>;
}

/** Small segmented control that flips a form section between the row editor and a raw JSON editor. */
export default function SectionModeToggle({ mode, onChange, disabled }: SectionModeToggleProps) {
  const options: Array<{ value: SectionEditMode; label: string; icon: typeof List }> = [
    { value: 'rows', label: 'Form', icon: List },
    { value: 'json', label: 'JSON', icon: Braces },
  ];
  return (
    <div className="inline-flex items-center rounded-lg border border-border bg-muted/50 p-0.5">
      {options.map(({ value, label, icon: Icon }) => {
        const blockedReason = disabled?.[value];
        return (
        <button
          key={value}
          type="button"
          onClick={() => onChange(value)}
          disabled={Boolean(blockedReason)}
          title={blockedReason}
          aria-pressed={mode === value}
          className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-medium transition-colors ${
            mode === value
              ? 'bg-background text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground'
          } ${blockedReason ? 'cursor-not-allowed opacity-40' : ''}`}
        >
          <Icon className="h-3 w-3" />
          {label}
        </button>
        );
      })}
    </div>
  );
}
