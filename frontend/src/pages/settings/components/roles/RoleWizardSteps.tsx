/**
 * RoleWizardSteps
 *
 * Step indicator / navigation for the role editor wizard.
 */

import { Check } from 'lucide-react';
import { cn } from '../../../../lib/utils';
import type { WizardStep } from './constants';

interface RoleWizardStepsProps {
  steps: { key: WizardStep; label: string }[];
  currentIndex: number;
  /** Whether the user may advance past the current step. */
  canAdvance: boolean;
  onSelect: (key: WizardStep) => void;
}

export default function RoleWizardSteps({ steps, currentIndex, canAdvance, onSelect }: RoleWizardStepsProps) {
  return (
    <nav
      aria-label="Role editor steps"
      className="flex items-center gap-2 border-b border-border bg-muted/50 px-6 py-3"
    >
      {steps.map((s, i) => {
        const isActive = i === currentIndex;
        const isComplete = i < currentIndex;
        // A step is reachable when going back/staying, or when advancing is allowed.
        const reachable = i <= currentIndex || canAdvance;
        return (
          <button
            key={s.key}
            type="button"
            onClick={() => reachable && onSelect(s.key)}
            disabled={!reachable}
            aria-current={isActive ? 'step' : undefined}
            className={cn(
              'flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cobalt/40 disabled:cursor-not-allowed',
              isActive
                ? 'bg-cobalt text-white'
                : isComplete
                  ? 'bg-success-subtle text-success'
                  : 'bg-accent text-muted-foreground',
            )}
          >
            {isComplete ? (
              <Check className="h-3.5 w-3.5" />
            ) : (
              <span className="h-4 w-4 text-center text-xs leading-4">{i + 1}</span>
            )}
            {s.label}
          </button>
        );
      })}
    </nav>
  );
}
