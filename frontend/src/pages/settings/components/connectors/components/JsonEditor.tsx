import { AlertCircle } from 'lucide-react';

interface JsonEditorProps {
  value: string;
  onChange: (value: string) => void;
  /** Parse error to surface under the editor; null when the JSON is valid. */
  error: string | null;
  rows?: number;
  placeholder?: string;
  onFocus?: () => void;
}

/** Monospace JSON textarea with inline validation feedback. */
export default function JsonEditor({
  value,
  onChange,
  error,
  rows = 6,
  placeholder,
  onFocus,
}: JsonEditorProps) {
  return (
    <div className="space-y-1">
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={onFocus}
        rows={rows}
        placeholder={placeholder}
        spellCheck={false}
        className={`w-full resize-y rounded-md border bg-background px-3 py-2 font-mono text-xs leading-5 focus:outline-none focus:ring-1 ${
          error
            ? 'border-destructive/30 focus:ring-destructive/30'
            : 'border-input focus:ring-primary'
        }`}
      />
      {error && (
        <p className="flex items-start gap-1 text-[11px] text-destructive">
          <AlertCircle className="mt-0.5 h-3 w-3 shrink-0" />
          <span>{error}</span>
        </p>
      )}
    </div>
  );
}
