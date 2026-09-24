/**
 * Theme Contract
 *
 * A small, curated set of per-organization theme tokens. These map onto the
 * CSS custom properties defined in `index.css` (`:root`). Defaults mirror the
 * built-in cobalt theme, so an organization without a saved theme renders
 * identically to the default styling.
 */

/** Curated font option for the application typeface. */
export interface FontOption {
  /** Stable key persisted in org settings. */
  id: string;
  /** Human-readable name shown in the picker. */
  label: string;
  /** CSS font-family value applied to `--font-sans` / `--font-heading`. */
  stack: string;
  /**
   * Google Fonts stylesheet URL to inject at runtime. Omitted for fonts that
   * are bundled (Inter) or always available (system stack).
   */
  googleHref?: string;
}

/** Curated typefaces selectable as the application font. */
export const FONT_OPTIONS: FontOption[] = [
  {
    id: 'inter',
    label: 'Inter',
    stack:
      "'Inter Variable', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
  },
  {
    id: 'system',
    label: 'System Default',
    stack:
      "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
  },
  {
    id: 'roboto',
    label: 'Roboto',
    stack: "'Roboto', system-ui, sans-serif",
    googleHref:
      'https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;600;700&display=swap',
  },
  {
    id: 'open-sans',
    label: 'Open Sans',
    stack: "'Open Sans', system-ui, sans-serif",
    googleHref:
      'https://fonts.googleapis.com/css2?family=Open+Sans:wght@400;500;600;700&display=swap',
  },
  {
    id: 'poppins',
    label: 'Poppins',
    stack: "'Poppins', system-ui, sans-serif",
    googleHref:
      'https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap',
  },
  {
    id: 'lato',
    label: 'Lato',
    stack: "'Lato', system-ui, sans-serif",
    googleHref:
      'https://fonts.googleapis.com/css2?family=Lato:wght@400;700&display=swap',
  },
  {
    id: 'helvetica-neue',
    label: 'Helvetica Neue',
    stack: "'Helvetica Neue', Helvetica, Arial, sans-serif",
  },
  {
    id: 'custom',
    label: 'Custom font',
    stack: 'system-ui, sans-serif',
  },
];

/** Resolve a font option by id, falling back to the default (Inter). */
export function getFontOption(fontId: string): FontOption {
  return FONT_OPTIONS.find((f) => f.id === fontId) ?? FONT_OPTIONS[0];
}

/** Selectable top-bar height presets, expressed as a percentage of the viewport. */
export const HEADER_SIZE_OPTIONS: Array<{ label: string; value: string }> = [
  { label: 'Compact', value: '5%' },
  { label: 'Default', value: '7%' },
  { label: 'Tall', value: '10%' },
  { label: 'Extra large', value: '12%' },
];

/**
 * Selectable base font-size presets (CSS `px`). This sets the root rem unit, so
 * the chosen size scales all text and rem-based spacing/components together.
 */
export const FONT_SIZE_OPTIONS: Array<{ label: string; value: string }> = [
  { label: 'Compact', value: '12px' },
  { label: 'Small', value: '13px' },
  { label: 'Default', value: '15px' },
  { label: 'Large', value: '16px' },
  { label: 'Extra large', value: '18px' },
  { label: 'Maximum', value: '20px' },
];

/**
 * Selectable box-shadow presets for cards and elevated surfaces.
 * Applied via the `--element-shadow` CSS variable.
 */
export const SHADOW_OPTIONS: Array<{ label: string; value: string }> = [
  { label: 'None', value: 'none' },
  { label: 'Subtle', value: '0 1px 3px 0 rgba(0,0,0,0.1), 0 1px 2px -1px rgba(0,0,0,0.1)' },
  { label: 'Default', value: '0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -2px rgba(0,0,0,0.1)' },
  { label: 'Elevated', value: '0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -4px rgba(0,0,0,0.1)' },
  { label: 'Dramatic', value: '0 20px 25px -5px rgba(0,0,0,0.15), 0 8px 10px -6px rgba(0,0,0,0.15)' },
];

/** Selectable navigation placements. */
export const NAV_LAYOUT_OPTIONS: Array<{ label: string; value: NavLayout }> = [
  { label: 'Sidebar', value: 'sidebar' },
  { label: 'Top bar', value: 'topbar' },
];

/** Where the main navigation is rendered. */
export type NavLayout = 'sidebar' | 'topbar';

/**
 * Selectable page-content max-width presets. Applied via the
 * `--content-max-width` CSS variable; `none` lets content span the full window.
 */
export const CONTENT_WIDTH_OPTIONS: Array<{ label: string; value: string }> = [
  { label: 'Full width', value: 'none' },
  { label: 'Wide (1600px)', value: '1600px' },
  { label: 'Compact (1280px)', value: '1280px' },
];

/** The editable per-organization theme tokens. */
export interface OrgTheme {
  /**
   * Main navigation placement: the classic left sidebar, or a horizontal nav
   * inside the top bar. Defaults to 'sidebar' when omitted.
   */
  navLayout?: NavLayout;
  /**
   * Max width of the page content area (CSS max-width value, e.g. `1600px`,
   * or `none` for full width). Content centers when narrower than the window.
   * Defaults to `1600px` when omitted. See {@link CONTENT_WIDTH_OPTIONS}.
   */
  contentWidth?: string;
  /** Brand/primary color (any valid CSS color, e.g. `#0047AB`). */
  brandColor: string;
  /** Foreground color used on top of the brand color (text on buttons). */
  brandForeground: string;
  /** Base corner radius (CSS length, e.g. `0.625rem`). Drives the radius scale. */
  radius: string;
  /** Font option id (see {@link FONT_OPTIONS}). */
  fontId: string;
  /**
   * Base font size as a CSS `px` length (e.g. `15px`). Drives the root rem unit,
   * so it scales all text and rem-based spacing/components. See
   * {@link FONT_SIZE_OPTIONS}.
   */
  fontSize: string;
  /**
   * Top-bar height as a percentage of the viewport (e.g. `7%`). Applied as a
   * `vh` unit so the bar scales with the screen. See {@link HEADER_SIZE_OPTIONS}.
   */
  headerHeight: string;
  /**
   * Top-bar background color (any valid CSS color). The matching text/icon color
   * is derived automatically from this color's luminance, so a dark header keeps
   * its content readable without a separate setting.
   */
  headerColor: string;
  /**
   * Background color for modal / dialog / slide-over title bars (any valid CSS
   * color). Independent of {@link headerColor}; its text/icon color is likewise
   * derived from the chosen color's luminance.
   */
  modalColor: string;
  /**
   * Box-shadow applied to cards and elevated surfaces via `--element-shadow`.
   * Use a value from {@link SHADOW_OPTIONS} or any valid CSS box-shadow string.
   * Defaults to 'none' when omitted.
   */
  elementShadow?: string;
  /**
   * Background color for the main page content area (any valid CSS color).
   * Defaults to the platform's built-in white when omitted.
   */
  contentBackground?: string;
  /**
   * CSS font-family stack for the custom font option.
   * Only used when `fontId` is `'custom'`.
   * Example: `"'Nunito', sans-serif"`
   */
  customFontFamily?: string;
  /**
   * Stylesheet URL (Google Fonts or self-hosted) to inject when `fontId` is
   * `'custom'`. Optional — omit when the font is already available in the page.
   * Example: `"https://fonts.googleapis.com/css2?family=Nunito:wght@400;700&display=swap"`
   */
  customFontHref?: string;
}

/** Default theme — matches the built-in cobalt styling in `index.css`. */
export const DEFAULT_THEME: OrgTheme = {
  navLayout: 'sidebar',
  contentWidth: '1600px',
  brandColor: '#0047AB',
  brandForeground: '#FFFFFF',
  radius: '0.625rem',
  fontId: 'inter',
  fontSize: '15px',
  headerHeight: '7%',
  headerColor: '#FFFFFF',
  modalColor: '#FFFFFF',
};

/**
 * Merge a (possibly partial) persisted theme over the defaults so that missing
 * fields fall back to the built-in values. Accepts an optional `skinDefaults`
 * layer that sits between the global defaults and the per-org overrides, so a
 * skin can enforce its own branding (e.g. font) without overriding org choices.
 */
export function normalizeTheme(
  partial: Partial<OrgTheme> | null | undefined,
  skinDefaults?: Partial<OrgTheme>,
): OrgTheme {
  return { ...DEFAULT_THEME, ...(skinDefaults ?? {}), ...(partial ?? {}) };
}

/**
 * Extract the theme from an organization's `settings` blob. When `skinDefaults`
 * is provided (from `SkinManifest.defaultTheme`), it sits between the global
 * defaults and any org-level overrides — ensuring skin-declared branding (e.g.
 * the deployment font) applies when the org hasn't set its own preference.
 */
export function themeFromSettings(
  settings: Record<string, unknown> | null | undefined,
  skinDefaults?: Partial<OrgTheme>,
): OrgTheme {
  const raw = settings?.theme;
  if (raw && typeof raw === 'object') {
    return normalizeTheme(raw as Partial<OrgTheme>, skinDefaults);
  }
  return normalizeTheme(null, skinDefaults);
}
