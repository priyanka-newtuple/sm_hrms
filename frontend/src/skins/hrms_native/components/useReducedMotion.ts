import { useEffect, useState } from 'react';

const REDUCED_MOTION = '(prefers-reduced-motion: reduce)';
// Some environments (tests, very old browsers) have no matchMedia; treat them as no preference.
const mediaQuery = () => (typeof window !== 'undefined' && typeof window.matchMedia === 'function' ? window.matchMedia(REDUCED_MOTION) : null);

/** Tracks the operating-system reduced-motion preference so every effect can opt out together. */
export function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(() => mediaQuery()?.matches ?? false);
  useEffect(() => {
    const query = mediaQuery();
    if (!query) return;
    const update = () => setReduced(query.matches);
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);
  return reduced;
}
