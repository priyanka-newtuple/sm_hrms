import { AlertCircle, AlertTriangle, CheckCircle2 } from 'lucide-react';
import type { ValidationIssue } from '@/lib/state-machine/types';
import { Button } from '@/components/ui/button';

export type WizardStep = 'basics' | 'stages' | 'transitions' | 'guards';

interface ValidationPanelProps {
  issues: ValidationIssue[];
  activeStep: WizardStep;
  onNavigateToStep: (step: WizardStep) => void;
}

export function pathToStep(path: string): WizardStep {
  if (path.startsWith('transitions') && path.includes('.guards')) return 'guards';
  if (path.startsWith('transitions')) return 'transitions';
  if (path.startsWith('states') || path === 'initial_state' || path.startsWith('definition.entity_schema')) return 'stages';
  return 'basics';
}

export default function ValidationPanel({ issues, activeStep, onNavigateToStep }: ValidationPanelProps) {
  const errors = issues.filter((i) => i.level === 'error');
  const warnings = issues.filter((i) => i.level === 'warning');

  return (
    <aside className="w-72 shrink-0 border-l border-border bg-muted/50 p-4 space-y-4 overflow-y-auto max-h-[600px]">
      <h3 className="text-sm font-semibold text-foreground">Validation</h3>

      {issues.length === 0 ? (
        <div className="flex items-center gap-2 text-sm text-success bg-success-subtle px-3 py-2 rounded-lg">
          <CheckCircle2 className="w-4 h-4" />
          No issues
        </div>
      ) : (
        <>
          {errors.length > 0 && (
            <section>
              <h4 className="text-xs font-medium text-destructive uppercase tracking-wide mb-2 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                Errors ({errors.length})
              </h4>
              <ul className="space-y-2">
                {errors.map((issue, i) => {
                  const targetStep = pathToStep(issue.path);
                  const isActive = targetStep === activeStep;
                  return (
                    <li key={`err-${i}`}>
                      <Button variant="primary"
                        onClick={() => onNavigateToStep(targetStep)}
                        className={`w-full text-left text-xs px-2 py-1.5 rounded border ${
                          isActive
                            ? 'bg-destructive-subtle border-destructive/30 text-destructive'
                            : 'bg-card border-destructive/30 text-destructive hover:bg-destructive-subtle'
                        }`}
                      >
                        <div className="font-mono text-[10px] text-muted-foreground">{issue.path}</div>
                        <div>{issue.message}</div>
                      </Button>
                    </li>
                  );
                })}
              </ul>
            </section>
          )}

          {warnings.length > 0 && (
            <section>
              <h4 className="text-xs font-medium text-warning uppercase tracking-wide mb-2 flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" />
                Warnings ({warnings.length})
              </h4>
              <ul className="space-y-2">
                {warnings.map((issue, i) => {
                  const targetStep = pathToStep(issue.path);
                  const isActive = targetStep === activeStep;
                  return (
                    <li key={`warn-${i}`}>
                      <Button variant="primary"
                        onClick={() => onNavigateToStep(targetStep)}
                        className={`w-full text-left text-xs px-2 py-1.5 rounded border ${
                          isActive
                            ? 'bg-warning-subtle border-warning/30 text-warning'
                            : 'bg-card border-warning/30 text-warning hover:bg-warning-subtle'
                        }`}
                      >
                        <div className="font-mono text-[10px] text-muted-foreground">{issue.path}</div>
                        <div>{issue.message}</div>
                      </Button>
                    </li>
                  );
                })}
              </ul>
            </section>
          )}
        </>
      )}
    </aside>
  );
}
