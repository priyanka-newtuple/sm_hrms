import { useCallback, useRef } from 'react';

const STORAGE_KEY = 'pipeline_assignee_filter_frequency_v1';
// Safety cap so a long-lived browser profile touching many orgs/boards over
// time doesn't grow this unboundedly — keep only the most-used entries.
const MAX_TRACKED = 200;

type FrequencyMap = Record<string, number>;

function readFrequency(): FrequencyMap {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    // Private browsing / storage disabled — frequency tracking is a
    // nice-to-have personalization, not a feature anything else depends on.
    return {};
  }
}

function writeFrequency(freq: FrequencyMap): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(freq));
  } catch {
    // Same as above — fail silently.
  }
}

function prune(freq: FrequencyMap): FrequencyMap {
  const ids = Object.keys(freq);
  if (ids.length <= MAX_TRACKED) return freq;
  return Object.fromEntries(
    ids
      .sort((a, b) => freq[b] - freq[a])
      .slice(0, MAX_TRACKED)
      .map((id) => [id, freq[id]]),
  );
}

/**
 * Tracks how often this browser's user picks each assignee from the
 * filter-by-assignee control, purely client-side (localStorage) — so
 * AssigneeAvatarFilter can promote frequently-picked people into the visible
 * avatar row instead of always showing the same fixed slate while whoever
 * this person actually filters by most stays buried behind "+N".
 */
export function useAssigneeFilterFrequency() {
  // Lazy-read once per mount, then keep in a ref: a selection updates the
  // ref synchronously before the caller's own state update re-renders the
  // consuming component, so the new value is already there to read.
  const cacheRef = useRef<FrequencyMap | null>(null);

  const getAll = useCallback((): FrequencyMap => {
    if (!cacheRef.current) cacheRef.current = readFrequency();
    return cacheRef.current;
  }, []);

  const recordSelection = useCallback(
    (id: string) => {
      const current = getAll();
      const next = prune({ ...current, [id]: (current[id] ?? 0) + 1 });
      cacheRef.current = next;
      writeFrequency(next);
    },
    [getAll],
  );

  return { getAll, recordSelection };
}
