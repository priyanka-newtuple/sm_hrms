import { Eye, EyeOff } from 'lucide-react';

interface PipelineTerminalToggleProps {
  /** True when terminal-state entities are currently hidden. */
  hidden: boolean;
  /** Display label of the terminal state(s), e.g. "Rejected" or "Terminal". */
  label: string;
  /** Called with the next hidden value when the control is clicked. May persist asynchronously. */
  onToggle: (hidden: boolean) => void | Promise<void>;
}

/**
 * A Show / Hide toggle for entities that have reached a terminal state.
 * The label flips to the action: "Hide <state>" while they are shown,
 * "Show <state>" while they are hidden. Styled to match the neighbouring
 * board filter controls (BoardFilterBar `INPUT_CLASS`).
 */
export default function PipelineTerminalToggle({ hidden, label, onToggle }: PipelineTerminalToggleProps) {
  const text = hidden ? `Show ${label}` : `Hide ${label}`;
  return (
    <button
      type="button"
      onClick={() => onToggle(!hidden)}
      aria-pressed={hidden}
      title={text}
      className="flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-border bg-muted/50 px-3 text-sm text-foreground transition-colors hover:bg-muted focus:border-cobalt/40 focus:outline-none focus:ring-2 focus:ring-cobalt/10"
    >
      {hidden ? <Eye className="h-4 w-4 text-muted-foreground" /> : <EyeOff className="h-4 w-4 text-muted-foreground" />}
      <span>{text}</span>
    </button>
  );
}
