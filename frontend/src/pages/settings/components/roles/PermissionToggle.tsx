/**
 * PermissionToggle
 *
 * Accessible on/off toggle used across the role permission matrices.
 * Renders a real <button> with aria-pressed and an accessible label, with
 * static tone classes (no dynamic Tailwind).
 */

import type { ReactNode } from 'react';
import { cn } from '../../../../lib/utils';

type OnTone = 'success' | 'cobalt' | 'amber';
type OffTone = 'neutral' | 'danger';

// Each tone is a tint of its own color with the solid color as the icon, so
// hover deepens the tint rather than filling with the solid — filling would
// make the icon exactly its own background and hide it.
const onToneStyles: Record<OnTone, string> = {
  success: 'bg-success/10 text-success hover:bg-success/20',
  cobalt: 'bg-cobalt/10 text-cobalt hover:bg-cobalt/20',
  amber: 'bg-warning/10 text-warning hover:bg-warning/20',
};

const offToneStyles: Record<OffTone, string> = {
  neutral: 'bg-muted text-muted-foreground hover:bg-accent',
  danger: 'bg-destructive/10 text-destructive hover:bg-destructive/20',
};

interface PermissionToggleProps {
  pressed: boolean;
  onToggle: () => void;
  /** Accessible label describing what this toggle controls. */
  label: string;
  onIcon: ReactNode;
  offIcon: ReactNode;
  tone?: OnTone;
  offTone?: OffTone;
  className?: string;
}

export default function PermissionToggle({
  pressed,
  onToggle,
  label,
  onIcon,
  offIcon,
  tone = 'success',
  offTone = 'neutral',
  className,
}: PermissionToggleProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={pressed}
      aria-label={label}
      title={label}
      className={cn(
        'inline-flex h-8 w-8 items-center justify-center rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cobalt/40',
        pressed ? onToneStyles[tone] : offToneStyles[offTone],
        className,
      )}
    >
      {pressed ? onIcon : offIcon}
    </button>
  );
}
