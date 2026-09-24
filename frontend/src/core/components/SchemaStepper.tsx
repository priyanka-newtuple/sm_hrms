import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { FormSchema } from '@/core/types';

interface Step {
  key: string;
  label: string;
  index: number;
}

interface SchemaStepperProps {
  schemas: FormSchema[];
  activeIndex: number;
  showReview?: boolean;
  onSelect?: (index: number) => void;
}

export default function SchemaStepper({ schemas, activeIndex, showReview, onSelect }: SchemaStepperProps) {
  if (schemas.length <= 1) return null;

  const steps: Step[] = [
    ...schemas.map((s, i) => ({ key: s.schema_key, label: s.name, index: i })),
    ...(showReview ? [{ key: '__review__', label: 'Review & Confirm', index: schemas.length }] : []),
  ];

  return (
    <div className="flex flex-shrink-0 items-start bg-muted/50 px-8 py-6 border-b border-border">
      {steps.map((step, pos) => {
        const isCompleted = step.index < activeIndex;
        const isActive = step.index === activeIndex;
        const isFirst = pos === 0;
        const isLast = pos === steps.length - 1;

        return (
          <div key={step.key} className="flex flex-1 flex-col items-center">
            <div className="flex w-full items-center">
              <div className={cn('h-px flex-1', isFirst ? 'invisible' : 'bg-accent')} />
              <button
                type="button"
                onClick={() => onSelect?.(step.index)}
                className={cn(
                  'flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full text-sm font-semibold transition-colors',
                  isCompleted
                    ? 'cursor-pointer bg-success/90 text-success-foreground hover:bg-success'
                    : isActive
                      ? 'bg-primary text-primary-foreground'
                      : 'cursor-pointer bg-accent text-muted-foreground hover:bg-accent/70 hover:text-foreground',
                )}
              >
                {isCompleted ? <Check className="h-6 w-6" /> : step.index + 1}
              </button>
              <div className={cn('h-px flex-1', isLast ? 'invisible' : 'bg-accent')} />
            </div>
            <span
              className={cn(
                'mt-2 px-1 text-center text-sm leading-tight',
                isActive || isCompleted ? 'text-foreground' : 'text-muted-foreground',
              )}
            >
              {step.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
