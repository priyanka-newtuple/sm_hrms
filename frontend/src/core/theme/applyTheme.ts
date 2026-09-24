/**
 * Runtime Theme Applier
 *
 * Applies an {@link OrgTheme} to the document by overriding the CSS custom
 * properties declared in `index.css`. The applied theme is cached in
 * localStorage so a returning user's branding paints on the first frame,
 * before the active organization has loaded from the API.
 */

import {
  applyMode,
  currentMode,
  getStoredPreference,
  resolveMode,
  setDarkAllowed,
  type ThemeMode,
} from './mode';
import {
  DEFAULT_THEME,
  getFontOption,
  normalizeTheme,
  type OrgTheme,
} from './themeTypes';

/** localStorage key holding the last applied theme. */
const THEME_CACHE_KEY = 'app_theme';

/**
 * The theme currently painted on the document — which is not always the cached
 * one. Branding's live preview applies an unsaved draft with `cache: false`, so
 * the cache holds the last *saved* theme while the screen shows the draft.
 * `reapplyThemeForMode` re-derives from this, not from the cache, so flipping
 * light/dark mid-edit keeps the draft on screen.
 */
let appliedTheme: OrgTheme | null = null;

/** Identifier for the dynamically injected font stylesheet link. */
const FONT_LINK_ID = 'app-theme-font';

/**
 * Amounts by which the brand color is shifted to derive the `--brand-light`
 * (toward white) and `--brand-dark` (toward black) palette tokens. See
 * {@link shadeHex} for the sign convention.
 */
const BRAND_LIGHT_SHADE = 0.12;
const BRAND_DARK_SHADE = -0.18;

/** Parse a `#rrggbb` / `#rgb` string into RGB components, or null if not hex. */
function parseHex(color: string): { r: number; g: number; b: number } | null {
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(color.trim());
  if (!m) return null;
  let hex = m[1];
  if (hex.length === 3) hex = hex.split('').map((c) => c + c).join('');
  return {
    r: parseInt(hex.slice(0, 2), 16),
    g: parseInt(hex.slice(2, 4), 16),
    b: parseInt(hex.slice(4, 6), 16),
  };
}

/**
 * Perceived luminance (0–1) of a hex color, using the usual sRGB coefficients.
 * Returns 0 for non-hex colors so they are treated as "already dark" and left
 * untouched by the dark-mode substitutions below.
 */
function luminance(color: string): number {
  const rgb = parseHex(color);
  if (!rgb) return 0;
  return (0.299 * rgb.r + 0.587 * rgb.g + 0.114 * rgb.b) / 255;
}

/** Above this, a color is treated as "chosen for a light UI". */
const LIGHT_SURFACE_THRESHOLD = 0.6;

/**
 * Pick a readable foreground (near-black or white) for text/icons placed on top
 * of the given background color, based on its relative luminance. Falls back to
 * white for non-hex colors so a custom CSS color never yields invisible text.
 */
function readableForeground(background: string): string {
  return luminance(background) > LIGHT_SURFACE_THRESHOLD ? '#111111' : '#FFFFFF';
}

/**
 * Clamp a header-height percentage to a usable range and express it as a `vh`
 * unit so the bar scales with the viewport. Falls back to the default when the
 * stored value is not a plain percentage.
 */
function headerHeightVh(height: string): string {
  const m = /^(\d+(?:\.\d+)?)%$/.exec(height.trim());
  const pct = m ? Math.min(15, Math.max(5, parseFloat(m[1]))) : 7;
  return `${pct}vh`;
}

/**
 * Clamp the base font size to a sane `px` range so a stored value can never make
 * the whole UI unusably small or large. Falls back to the default when the value
 * is not a plain `px` length.
 */
function baseFontSizePx(size: string): string {
  const m = /^(\d+(?:\.\d+)?)px$/.exec(size.trim());
  const px = m ? Math.min(20, Math.max(12, parseFloat(m[1]))) : 15;
  return `${px}px`;
}

/**
 * Shift a hex color toward white (percent > 0) or black (percent < 0).
 * Returns the original string unchanged when it is not a hex color.
 */
function shadeHex(color: string, percent: number): string {
  const rgb = parseHex(color);
  if (!rgb) return color;
  const target = percent < 0 ? 0 : 255;
  const ratio = Math.abs(percent);
  const mix = (c: number) => Math.round((target - c) * ratio + c);
  const toHex = (c: number) => mix(c).toString(16).padStart(2, '0');
  return `#${toHex(rgb.r)}${toHex(rgb.g)}${toHex(rgb.b)}`;
}

/**
 * A brand color below this luminance is too dark to read against the dark-mode
 * background and gets raised to {@link BRAND_DARK_MODE_TARGET_L} HSL lightness.
 */
const BRAND_DARK_MODE_FLOOR = 0.35;
const BRAND_DARK_MODE_TARGET_L = 0.5;

/**
 * Raise a hex color's HSL lightness to `targetL`, keeping hue and saturation.
 *
 * Deliberately not {@link shadeHex}: mixing toward white also washes the color
 * out, turning a confident brand blue into a dusty grey-blue on the dark page.
 * Lifting lightness alone keeps the brand recognisable — the "use a brighter
 * variant, not a tinted one" rule.
 */
function liftLightness(color: string, targetL: number): string {
  const rgbc = parseHex(color);
  if (!rgbc) return color;

  const r = rgbc.r / 255;
  const g = rgbc.g / 255;
  const b = rgbc.b / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (l >= targetL) return color;

  const d = max - min;
  const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
  let h = 0;
  if (d !== 0) {
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h *= 60;
    if (h < 0) h += 360;
  }

  const c = (1 - Math.abs(2 * targetL - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = targetL - c / 2;
  const [r1, g1, b1] =
    h < 60 ? [c, x, 0]
    : h < 120 ? [x, c, 0]
    : h < 180 ? [0, c, x]
    : h < 240 ? [0, x, c]
    : h < 300 ? [x, 0, c]
    : [c, 0, x];

  const hex = (v: number) =>
    Math.round(Math.min(1, Math.max(0, v + m)) * 255)
      .toString(16)
      .padStart(2, '0');
  return `#${hex(r1)}${hex(g1)}${hex(b1)}`;
}

/**
 * Resolve one of the org's configurable surface colors (top bar, modal title
 * bar) for the active mode.
 *
 * These colors are picked against the light UI, so in dark mode a light one
 * would punch a white hole in the page — it is replaced by the neutral `--card`
 * surface. A color the org deliberately made dark or saturated is kept, and its
 * foreground is derived as usual.
 */
export function surfaceForMode(
  color: string,
  mode: ThemeMode,
): { background: string; foreground: string } {
  if (mode === 'dark' && luminance(color) > LIGHT_SURFACE_THRESHOLD) {
    return { background: 'var(--card)', foreground: 'var(--card-foreground)' };
  }
  return { background: color, foreground: readableForeground(color) };
}

/**
 * Resolve the main content-area background for the active mode. Unset, empty
 * and light-in-dark-mode all fall back to the `--background` token.
 */
export function contentBackgroundForMode(
  color: string | undefined,
  mode: ThemeMode,
): string {
  if (!color) return 'var(--background)';
  if (mode === 'dark' && luminance(color) > LIGHT_SURFACE_THRESHOLD) {
    return 'var(--background)';
  }
  return color;
}

/**
 * Resolve the brand color for the active mode: unchanged in light, brightened
 * in dark when it is dark enough to lose contrast against the dark background.
 * Non-hex colors are returned unchanged.
 */
export function brandForMode(color: string, mode: ThemeMode): string {
  if (mode === 'dark' && luminance(color) < BRAND_DARK_MODE_FLOOR) {
    return liftLightness(color, BRAND_DARK_MODE_TARGET_L);
  }
  return color;
}

/**
 * CSS custom properties (declared on `:root` in index.css) driven by each
 * editable theme token. Setting these on `document.documentElement` overrides
 * the stylesheet defaults at runtime.
 */
function cssVariablesFor(theme: OrgTheme, mode: ThemeMode): Record<string, string> {
  const font = getFontOption(theme.fontId);
  const fontStack =
    theme.fontId === 'custom'
      ? (theme.customFontFamily || 'system-ui, sans-serif')
      : font.stack;

  const brand = brandForMode(theme.brandColor, mode);
  // A lifted brand may no longer contrast with the org's stored foreground, so
  // re-derive it in that case; an unlifted brand keeps the org's choice.
  const brandForeground =
    brand === theme.brandColor ? theme.brandForeground : readableForeground(brand);
  const header = surfaceForMode(theme.headerColor, mode);
  const modal = surfaceForMode(theme.modalColor, mode);

  return {
    '--primary': brand,
    '--ring': brand,
    '--sidebar-primary': brand,
    '--sidebar-ring': brand,
    '--primary-foreground': brandForeground,
    '--sidebar-primary-foreground': brandForeground,
    // Brand palette (`bg-cobalt`, `text-cobalt`, `from-cobalt`, …) used across
    // the app outside the semantic `--primary` token. These resolve through the
    // `--brand*` indirection in index.css; light/dark shades are derived from
    // the brand color so those elements re-skin too.
    '--brand': brand,
    '--brand-light': shadeHex(brand, BRAND_LIGHT_SHADE),
    '--brand-dark': shadeHex(brand, BRAND_DARK_SHADE),
    '--radius': theme.radius,
    // Top bar: configurable height (as a viewport percentage) and background
    // color, with a foreground derived from the background's luminance so the
    // bar's text/icons stay readable on any chosen color.
    '--header-height': headerHeightVh(theme.headerHeight),
    '--header-background': header.background,
    '--header-foreground': header.foreground,
    // Modal / dialog / slide-over title bars — configured independently of the
    // main top bar, with the same luminance-derived foreground.
    '--modal-header-background': modal.background,
    '--modal-header-foreground': modal.foreground,
    // Font resolves through the `--app-font` indirection in index.css; the
    // `--font-sans`/`--font-heading` tokens are build-inlined and not
    // runtime-overridable, so we must set `--app-font` instead.
    '--app-font': fontStack,
    // Base rem size: drives the root font-size in index.css, scaling all
    // rem-based text/spacing/components uniformly.
    '--app-font-size': baseFontSizePx(theme.fontSize),
    // Card / surface elevation shadow — optional, defaults to none.
    '--element-shadow': theme.elementShadow ?? 'none',
    // Page content max-width — `none` spans the full window.
    '--content-max-width': theme.contentWidth ?? '1600px',
    // Main content area background — falls back to the built-in `--background`
    // token (pure white) when the org/skin hasn't chosen a custom color.
    '--content-background': contentBackgroundForMode(theme.contentBackground, mode),
  };
}

/** Inject (or remove) the Google Fonts stylesheet for the selected font. */
function applyFontLink(theme: OrgTheme): void {
  if (typeof document === 'undefined') return;
  const font = getFontOption(theme.fontId);
  const existing = document.getElementById(FONT_LINK_ID) as HTMLLinkElement | null;

  const href =
    theme.fontId === 'custom' ? (theme.customFontHref ?? '') : (font.googleHref ?? '');

  if (!href) {
    existing?.remove();
    return;
  }
  if (existing) {
    if (existing.href !== href) existing.href = href;
    return;
  }
  const link = document.createElement('link');
  link.id = FONT_LINK_ID;
  link.rel = 'stylesheet';
  link.href = href;
  document.head.appendChild(link);
}

/**
 * Apply a theme to the document and cache it for the next first paint.
 *
 * @param cache When false, the theme is applied but not persisted (used for
 *   live previews that should not survive a reload).
 */
export function applyTheme(partial: Partial<OrgTheme> | null | undefined, cache = true): void {
  if (typeof document === 'undefined') return;
  const theme = normalizeTheme(partial);
  const root = document.documentElement;

  for (const [name, value] of Object.entries(cssVariablesFor(theme, currentMode()))) {
    root.style.setProperty(name, value);
  }
  applyFontLink(theme);
  appliedTheme = theme;

  if (cache) {
    try {
      localStorage.setItem(THEME_CACHE_KEY, JSON.stringify(theme));
    } catch {
      // Ignore quota / privacy-mode failures — theming is best-effort.
    }
  }
}

/** Read the cached theme, or the default theme when nothing is cached. */
export function getCachedTheme(): OrgTheme {
  try {
    const raw = localStorage.getItem(THEME_CACHE_KEY);
    if (raw) return normalizeTheme(JSON.parse(raw) as Partial<OrgTheme>);
  } catch {
    // Ignore parse / access failures.
  }
  return DEFAULT_THEME;
}

/**
 * Apply the cached theme on first paint. Safe to call before React mounts.
 */
export function applyCachedTheme(): void {
  applyTheme(getCachedTheme(), false);
}

/**
 * Reset to the built-in default theme and clear the cache (e.g. on logout).
 *
 * The dark-mode permission is cleared too — it belongs to the organization the
 * user just left — which drops the page back to light. The user's own
 * light/dark preference is deliberately kept, so signing back into an org that
 * allows dark mode restores their choice without them re-picking it.
 */
export function resetTheme(): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  for (const name of Object.keys(cssVariablesFor(DEFAULT_THEME, currentMode()))) {
    root.style.removeProperty(name);
  }
  document.getElementById(FONT_LINK_ID)?.remove();
  appliedTheme = null;
  setDarkAllowed(null);
  applyMode(resolveMode(getStoredPreference()));
  try {
    localStorage.removeItem(THEME_CACHE_KEY);
  } catch {
    // Ignore.
  }
}

/**
 * Re-apply the organization theme against the mode now painted on `<html>`.
 * Called by the ThemeProvider after a mode flip, because the org theme is
 * written as inline custom properties that would otherwise still hold the
 * previous mode's derivations.
 *
 * Re-derives from whatever is on screen ({@link appliedTheme}), not from the
 * cache — Branding's live preview applies an unsaved draft without caching it,
 * and reading the cache here would silently revert that draft on a mode flip.
 *
 * No-op before any theme has been applied: pre-auth pages have no organization
 * and must keep the built-in styling.
 */
export function reapplyThemeForMode(): void {
  if (!appliedTheme) return;
  applyTheme(appliedTheme, false);
}
