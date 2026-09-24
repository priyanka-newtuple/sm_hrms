/**
 * Mode Context
 *
 * Kept out of the provider component file so that file exports a component and
 * nothing else, which is what `react-refresh/only-export-components` requires.
 */

import { createContext, useContext } from 'react';

import type { ThemePreference } from './mode';

export interface ThemeModeState {
  /** The user's preference — not necessarily the painted mode. */
  theme: ThemePreference;
  setTheme: (theme: ThemePreference) => void;
}

export const ThemeModeContext = createContext<ThemeModeState>({
  theme: 'system',
  setTheme: () => {},
});

/** Read and change the user's light/dark/system preference. */
export function useThemeMode(): ThemeModeState {
  return useContext(ThemeModeContext);
}
