import { useEffect, useState } from 'react';

function readStored<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw !== null ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

/**
 * Like {@link useState}, but persists the value to `localStorage` under `key`
 * so it survives reloads and revisits. Reads the stored value on first render
 * and whenever `key` changes, and writes back on every change.
 *
 * Falls back to `initial` (and silently ignores) when storage is unavailable
 * or the stored JSON is corrupt — never throws.
 *
 * @param key - localStorage key. Namespace it, e.g. `'pipeline-list:cols'`.
 * @param initial - value used when nothing is stored yet (or on read failure).
 */
export function usePersistentState<T>(
  key: string,
  initial: T,
): [T, React.Dispatch<React.SetStateAction<T>>] {
  const [state, setState] = useState<T>(() => readStored(key, initial));
  const [loadedKey, setLoadedKey] = useState(key);

  // A new key is a different slot, so re-read it instead of carrying the old
  // slot's value across — the write below would otherwise save the previous
  // key's value under the new one, destroying what was stored there. Adjusting
  // during render (rather than in an effect) means React re-renders before
  // committing, so the write never runs with the stale value.
  if (loadedKey !== key) {
    setLoadedKey(key);
    setState(readStored(key, initial));
  }

  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(state));
    } catch {
      /* storage full or unavailable — keep working in-memory */
    }
  }, [key, state]);

  return [state, setState];
}
