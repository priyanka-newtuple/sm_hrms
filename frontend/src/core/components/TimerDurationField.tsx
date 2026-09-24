/** Frontend-owned timer control whose final value is elapsed whole seconds. */

import { useEffect, useState } from 'react';
import { Loader2, Pause, Play, Square, Timer as TimerIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { formatElapsedDuration } from '../../shared/utils/entityDisplay';
import { calculateRecordedTimerSeconds } from '../../shared/hooks/useRecordTimer';

interface TimerDurationFieldProps {
  fieldKey: string;
  value: unknown;
  onChange: (value: unknown) => void;
  /** Enables a self-contained timer on saved-record read surfaces. */
  entityId?: string;
  disabled?: boolean;
  canStop?: boolean;
  stopBlockedHint?: string;
  /** Existing-record surfaces persist the final number here before Stop settles. */
  onStopped?: (elapsedSeconds: number) => void | Promise<void>;
  /** Container-owned state survives tabs/steps unmounting this component. */
  localStartedAt?: number | null;
  onLocalStart?: () => void;
  onLocalStop?: () => void;
  pausedAt?: number | null;
  pausedMs?: number;
  onPause?: () => void;
  onResume?: () => void;
  compact?: boolean;
}

export default function TimerDurationField({
  fieldKey,
  value,
  onChange,
  entityId,
  disabled,
  canStop = true,
  stopBlockedHint,
  onStopped,
  localStartedAt,
  onLocalStart,
  onLocalStop,
  pausedAt = null,
  pausedMs = 0,
  onPause,
  onResume,
  compact = false,
}: TimerDurationFieldProps) {
  const [internalStartedAt, setInternalStartedAt] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());

  const completedSeconds =
    typeof value === 'number' && Number.isFinite(value) ? Math.max(0, Math.floor(value)) : null;
  const timingEnabled = Boolean(onLocalStart || entityId);
  const startedAt = localStartedAt ?? internalStartedAt;
  const running = timingEnabled && startedAt !== null;
  const isPaused = running && pausedAt !== null;

  useEffect(() => {
    if (!running || isPaused) return;
    const interval = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [running, isPaused]);

  function handleStart() {
    setError(null);
    if (onLocalStart) onLocalStart();
    else if (entityId) setInternalStartedAt(Date.now());
    setNowMs(Date.now());
  }

  async function handleStop() {
    if (startedAt === null) return;
    const recorded = calculateRecordedTimerSeconds({
      baseSeconds: completedSeconds ?? 0,
      startedAt,
      pausedAt,
      pausedMs,
    });
    setBusy(true);
    setError(null);
    try {
      if (onStopped) await onStopped(recorded);
      else onChange(recorded);
      if (onLocalStop) onLocalStop();
      else setInternalStartedAt(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Failed to save timer');
    } finally {
      setBusy(false);
    }
  }

  const wrapperClass = compact
    ? 'flex items-center gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm'
    : 'flex items-center gap-2 rounded-xl border border-border bg-muted/50 px-4 py-3 text-base';

  if (!timingEnabled) {
    return (
      <div className={cn(wrapperClass, 'text-muted-foreground')} data-field-key={fieldKey}>
        <TimerIcon className="h-4 w-4 flex-shrink-0" />
        Available once the record is saved
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-2" data-field-key={fieldKey}>
        <div className="rounded-xl border border-destructive/30 bg-destructive-subtle px-4 py-2 text-sm text-destructive">
          {error}
        </div>
        <Button variant="outline" size="sm" onClick={() => setError(null)} disabled={disabled}>
          Retry
        </Button>
      </div>
    );
  }

  if (running) {
    const elapsed = calculateRecordedTimerSeconds({
      baseSeconds: completedSeconds ?? 0,
      startedAt,
      pausedAt,
      pausedMs,
      nowMs,
    });
    return (
      <div data-field-key={fieldKey}>
        <div className={wrapperClass}>
          {isPaused ? (
            <Pause className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
          ) : (
            <span className="relative flex h-2 w-2 flex-shrink-0">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cobalt opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-cobalt" />
            </span>
          )}
          <span className="text-foreground">
            {formatElapsedDuration(elapsed)}
            <span className="ml-1 text-sm text-muted-foreground">
              {isPaused ? 'paused' : 'and counting'}
            </span>
          </span>
          <div className="ml-auto flex items-center gap-2">
            {(onPause || onResume) && (
              <Button
                variant="outline"
                size="sm"
                onClick={isPaused ? onResume : onPause}
                disabled={disabled || busy}
              >
                {isPaused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
                {isPaused ? 'Resume' : 'Pause'}
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => void handleStop()}
              disabled={disabled || busy || isPaused || !canStop}
              title={isPaused ? 'Resume the timer before stopping it' : !canStop ? stopBlockedHint : undefined}
            >
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Square className="h-3.5 w-3.5" />}
              Stop
            </Button>
          </div>
        </div>
        {isPaused ? (
          <p className="mt-1 text-xs text-muted-foreground">
            Paused. Resume the timer to carry on filling this record in.
          </p>
        ) : !canStop && stopBlockedHint ? (
          <p className="mt-1 text-xs text-muted-foreground">{stopBlockedHint}</p>
        ) : null}
      </div>
    );
  }

  if (completedSeconds !== null) {
    return (
      <div className={wrapperClass} data-field-key={fieldKey}>
        <TimerIcon className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
        <span className="text-foreground">{formatElapsedDuration(completedSeconds)}</span>
        <span className="text-xs text-muted-foreground">stopped</span>
        {entityId && (
          <Button
            variant="outline"
            size="sm"
            className="ml-auto"
            onClick={handleStart}
            disabled={disabled || busy}
          >
            <Play className="h-3.5 w-3.5" />
            Resume
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className={wrapperClass} data-field-key={fieldKey}>
      <TimerIcon className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
      <span className="text-muted-foreground">Not started</span>
      <Button
        variant="outline"
        size="sm"
        className="ml-auto"
        onClick={handleStart}
        disabled={disabled || busy}
      >
        <Play className="h-3.5 w-3.5" />
        Start
      </Button>
    </div>
  );
}
