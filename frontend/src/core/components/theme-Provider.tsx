import { useEffect, useState, type ReactNode } from 'react';

import {
  ThemeModeContext,
  applyMode,
  getStoredPreference,
  reapplyThemeForMode,
  resolveMode,
  storePreference,
  watchSystemMode,
  type ThemePreference,
} from '../theme';

interface ThemeProviderProps {
  children: ReactNode;
  /** Preference used when the visitor has none stored yet. */
  defaultTheme?: ThemePreference;
}

/**
 * Owns the user's light/dark/system preference and keeps the document in sync
 * with it. The organization theme is re-applied on every mode flip because it
 * is written as inline custom properties that outrank the `.dark` class rules.
 */
export function ThemeProvider({ children, defaultTheme = 'system' }: ThemeProviderProps) {
  const [theme, setThemeState] = useState<ThemePreference>(
    () => getStoredPreference() ?? defaultTheme,
  );

  useEffect(() => {
    applyMode(resolveMode(theme));
    reapplyThemeForMode();
  }, [theme]);

  // Track the OS while the user has not pinned a mode.
  useEffect(() => {
    if (theme !== 'system') return;
    return watchSystemMode((mode) => {
      applyMode(mode);
      reapplyThemeForMode();
    });
  }, [theme]);

  const setTheme = (next: ThemePreference) => {
    storePreference(next);
    setThemeState(next);
  };

  return (
    <ThemeModeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeModeContext.Provider>
  );
}
