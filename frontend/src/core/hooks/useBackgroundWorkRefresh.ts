import { useCallback, useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { timelineKeys } from '@/core/services/api/queryKeys';

/**
 * When to re-check after an action that starts background work.
 *
 * A state's entry actions run in a worker, so they land *after* the API has
 * responded — and one action can fire the next transition, chaining several
 * states together. A single refresh on the response is therefore always too
 * early. These points cover a worker that finishes immediately, one that is
 * briefly queued, and a short chain of actions.
 */
const SETTLE_DELAYS_MS = [700, 2000, 4500] as const;

/**
 * Re-run a refresh after background work has had time to settle.
 *
 * `refresh` should be the caller's normal post-request refresh — it is invoked
 * again at each settle point, alongside an activity-timeline invalidation.
 * Returns a function to call once the triggering request has succeeded; it
 * cancels any re-checks still pending from a previous call.
 */
export function useBackgroundWorkRefresh(entityId: string, refresh: () => void): () => void {
  const queryClient = useQueryClient();
  const timers = useRef<number[]>([]);
  // Held in a ref so an inline arrow function from the caller does not
  // reschedule timers on every render.
  const refreshRef = useRef(refresh);
  useEffect(() => {
    refreshRef.current = refresh;
  }, [refresh]);

  const clearPending = useCallback(() => {
    timers.current.forEach(window.clearTimeout);
    timers.current = [];
  }, []);

  // Deliberately not cancelled on unmount. What these re-checks refresh belongs
  // to the parent — the board list and the open record — not to the component
  // that scheduled them. One caller closes the detail panel as part of handling
  // the transition, and cancelling there would drop the refresh at exactly the
  // moment the list behind it has gone stale. They are safe to run late: the
  // callback and the cache invalidation both target still-mounted parents, and
  // a superseding trigger clears anything still pending.

  return useCallback(() => {
    clearPending();
    timers.current = SETTLE_DELAYS_MS.map((delay) =>
      window.setTimeout(() => {
        refreshRef.current();
        void queryClient.invalidateQueries({ queryKey: timelineKeys.all(entityId) });
      }, delay),
    );
  }, [clearPending, entityId, queryClient]);
}
