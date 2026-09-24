import { useEffect } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  entityIteratorDirectionForKey,
  entityIteratorViewState,
  type EntityIteratorState,
} from '@/core/hooks/useEntityIterator';

interface EntityIteratorControlsProps extends EntityIteratorState {
  className?: string;
}

/** Previous/next navigation controls with a positional counter and Alt+Arrow shortcuts. */
export default function EntityIteratorControls({
  current,
  total,
  onPrevious,
  onNext,
  disabled = false,
  className,
}: EntityIteratorControlsProps) {
  const viewState = entityIteratorViewState(current, total, disabled);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target;
      const isEditableTarget =
        target instanceof HTMLElement
        && (target.isContentEditable
          || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName));
      if (isEditableTarget || event.ctrlKey || event.metaKey || event.shiftKey) return;

      const direction = entityIteratorDirectionForKey(
        event.key,
        event.altKey,
        current,
        total,
        disabled,
      );
      if (!direction) return;
      event.preventDefault();
      if (direction === -1) onPrevious();
      else onNext();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [current, total, disabled, onPrevious, onNext]);

  if (viewState.hidden) return null;

  return (
    <div className={`flex items-center gap-1 ${className ?? ''}`}>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={onPrevious}
        disabled={viewState.previousDisabled}
        aria-label="Previous entity"
        title="Previous entity"
        className="h-8 w-8 rounded-full"
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>
      <span
        className="min-w-14 text-center text-xs tabular-nums opacity-75"
        aria-label={`Entity ${viewState.label}`}
      >
        {viewState.label}
      </span>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={onNext}
        disabled={viewState.nextDisabled}
        aria-label="Next entity"
        title="Next entity"
        className="h-8 w-8 rounded-full"
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
    </div>
  );
}
