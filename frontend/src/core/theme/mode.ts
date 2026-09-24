/**
 * Light / Dark Mode
 *
 * The user's light/dark/system preference and the mechanics of painting it on
 * the document. Deliberately free of React so `main.tsx` can paint the mode
 * before the first frame, and free of the organization theme so pre-auth pages
 * can switch mode without an org context.
 */

/** A concrete rendering mode. Mirrored by the `dark` class on `<html>`. */
export type ThemeMode = 'light' | 'dark';

/** What the user chose. `system` tracks the OS setting live. */
export type ThemePreference = ThemeMode | 'system';

/** localStorage key holding the user's preference. */
export const MODE_STORAGE_KEY = 'vite-ui-theme';

/**
 * localStorage key caching whether the active organization allows dark mode
 * (the `darkModeEnabled` feature flag).
 *
 * The flag lives on the organization, which only loads after auth — but the
 * mode is painted before React mounts. This cache is how the flag reaches the
 * paint: AuthContext writes it when the org resolves, and both the inline
 * `<head>` script and `applyMode` below read it. Cleared on logout alongside
 * the org theme cache, so a logged-out visitor falls back to light.
 */
export const DARK_ALLOWED_KEY = 'app_dark_enabled';

/** The media query the `system` preference follows. */
const DARK_QUERY = '(prefers-color-scheme: dark)';

/**
 * Resolve a preference to the mode that should actually be painted. `system`
 * asks the OS; without a `window` (SSR, unit tests) it falls back to light.
 */
export function resolveMode(pref: ThemePreference): ThemeMode {
  if (pref === 'light' || pref === 'dark') return pref;
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return 'light';
  }
  return window.matchMedia(DARK_QUERY).matches ? 'dark' : 'light';
}

/** Read the persisted preference, defaulting to `system` for a new visitor. */
export function getStoredPreference(): ThemePreference {
  if (typeof localStorage === 'undefined') return 'system';
  try {
    const raw = localStorage.getItem(MODE_STORAGE_KEY);
    return raw === 'light' || raw === 'dark' || raw === 'system' ? raw : 'system';
  } catch {
    // Ignore privacy-mode failures — mode is best-effort.
    return 'system';
  }
}

/** Persist the user's preference. */
export function storePreference(pref: ThemePreference): void {
  try {
    localStorage.setItem(MODE_STORAGE_KEY, pref);
  } catch {
    // Ignore quota / privacy-mode failures.
  }
}

/**
 * Whether the active organization allows dark mode. Defaults to `false`: the
 * flag is opt-in, and a visitor with no cached value (logged out, first visit)
 * must not get a dark page.
 */
export function isDarkAllowed(): boolean {
  if (typeof localStorage === 'undefined') return false;
  try {
    return localStorage.getItem(DARK_ALLOWED_KEY) === 'true';
  } catch {
    // Ignore privacy-mode failures — treat as not allowed.
    return false;
  }
}

/** Cache the org's dark-mode permission. Pass `null` to clear it (logout). */
export function setDarkAllowed(allowed: boolean | null): void {
  try {
    if (allowed === null) localStorage.removeItem(DARK_ALLOWED_KEY);
    else localStorage.setItem(DARK_ALLOWED_KEY, String(allowed));
  } catch {
    // Ignore quota / privacy-mode failures.
  }
}

/**
 * Paint a mode by toggling the `dark` class the CSS variant keys off.
 *
 * The org permission is checked here rather than in {@link resolveMode} because
 * this is the only function that paints: ThemeProvider's `watchSystemMode`
 * callback applies the raw OS mode without going through `resolveMode`, so a
 * guard there would let an OS flip paint dark in an org that disabled it.
 */
export function applyMode(mode: ThemeMode): void {
  if (typeof document === 'undefined') return;
  document.documentElement.classList.toggle('dark', mode === 'dark' && isDarkAllowed());
}

/** The mode currently painted on the document. */
export function currentMode(): ThemeMode {
  if (typeof document === 'undefined') return 'light';
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
}

/**
 * Subscribe to OS-level mode changes. Callers should only subscribe while the
 * preference is `system`. Returns an unsubscribe function.
 */
export function watchSystemMode(onChange: (mode: ThemeMode) => void): () => void {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return () => {};
  }
  const mq = window.matchMedia(DARK_QUERY);
  const handler = (event: MediaQueryListEvent) => onChange(event.matches ? 'dark' : 'light');
  mq.addEventListener('change', handler);
  return () => mq.removeEventListener('change', handler);
}
