/** Frontend-owned state and arithmetic for one record-level timer session. */

import { useCallback, useState } from 'react';

interface RecordTimerState {
  /** Epoch ms the current session began, or null when stopped. */
  startedAt: number | null;
  /** Epoch ms the current pause began, or null while counting. */
  pausedAt: number | null;
  /** Total paused ms in the current session. */
  pausedMs: number;
}

const IDLE: RecordTimerState = { startedAt: null, pausedAt: null, pausedMs: 0 };

export interface RecordedTimerSecondsInput extends RecordTimerState {
  /** Previously saved elapsed seconds when a stopped timer is resumed. */
  baseSeconds?: number;
  /** Injectable clock for callers and deterministic tests. */
  nowMs?: number;
}

/** Add one local timer session to an already-recorded cumulative duration. */
export function calculateRecordedTimerSeconds({
  baseSeconds = 0,
  startedAt,
  pausedAt,
  pausedMs,
  nowMs = Date.now(),
}: RecordedTimerSecondsInput): number {
  const base = Number.isFinite(baseSeconds) ? Math.max(0, Math.floor(baseSeconds)) : 0;
  if (startedAt === null) return base;
  const activeMs = Math.max(0, (pausedAt ?? nowMs) - startedAt - Math.max(0, pausedMs));
  return base + Math.floor(activeMs / 1000);
}

export interface RecordTimer extends RecordTimerState {
  isRunning: boolean;
  isActive: boolean;
  isPaused: boolean;
  start: () => void;
  pause: () => void;
  resume: () => void;
  reset: () => void;
  recordedSeconds: (baseSeconds?: number, nowMs?: number) => number;
}

export function useRecordTimer(): RecordTimer {
  const [state, setState] = useState<RecordTimerState>(IDLE);

  const start = useCallback(
    () => setState({ startedAt: Date.now(), pausedAt: null, pausedMs: 0 }),
    [],
  );

  const pause = useCallback(() => {
    setState((prev) =>
      prev.startedAt === null || prev.pausedAt !== null
        ? prev
        : { ...prev, pausedAt: Date.now() },
    );
  }, []);

  const resume = useCallback(() => {
    setState((prev) =>
      prev.pausedAt === null
        ? prev
        : { ...prev, pausedAt: null, pausedMs: prev.pausedMs + (Date.now() - prev.pausedAt) },
    );
  }, []);

  const reset = useCallback(() => setState(IDLE), []);

  const recordedSeconds = useCallback(
    (baseSeconds = 0, nowMs = Date.now()) =>
      calculateRecordedTimerSeconds({ ...state, baseSeconds, nowMs }),
    [state],
  );

  return {
    ...state,
    isRunning: state.startedAt !== null && state.pausedAt === null,
    isActive: state.startedAt !== null,
    isPaused: state.pausedAt !== null,
    start,
    pause,
    resume,
    reset,
    recordedSeconds,
  };
}
