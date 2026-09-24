/**
 * Theme System Public Exports
 */

export {
  applyTheme,
  applyCachedTheme,
  brandForMode,
  contentBackgroundForMode,
  getCachedTheme,
  reapplyThemeForMode,
  resetTheme,
  surfaceForMode,
} from './applyTheme';

export {
  CONTENT_WIDTH_OPTIONS,
  DEFAULT_THEME,
  FONT_OPTIONS,
  FONT_SIZE_OPTIONS,
  HEADER_SIZE_OPTIONS,
  NAV_LAYOUT_OPTIONS,
  SHADOW_OPTIONS,
  getFontOption,
  normalizeTheme,
  themeFromSettings,
  type FontOption,
  type NavLayout,
  type OrgTheme,
} from './themeTypes';

export {
  DARK_ALLOWED_KEY,
  MODE_STORAGE_KEY,
  applyMode,
  currentMode,
  getStoredPreference,
  isDarkAllowed,
  resolveMode,
  setDarkAllowed,
  storePreference,
  watchSystemMode,
  type ThemeMode,
  type ThemePreference,
} from './mode';

export {
  ThemeModeContext,
  useThemeMode,
  type ThemeModeState,
} from './modeContext';
