/**
 * Skin utility helpers
 *
 * Pure functions for deriving display values from skin configuration.
 * No React or DOM dependencies — safe to use in hooks, components, and tests.
 */

// ---------------------------------------------------------------------------
// State color tokens
// ---------------------------------------------------------------------------

/**
 * All visual tokens derived from a single CSS color for one state/column.
 *
 * Use this instead of referencing the raw color string directly so that
 * every rendering site stays visually consistent.
 */
export interface StateDisplayTokens {
  /** Full-opacity color — for dots, icons, and active text */
  dot: string;
  /** ~10 % opacity tint — for subtle column/card backgrounds */
  background: string;
  /** ~20 % opacity tint — for borders and dividers */
  border: string;
  /** Full-opacity color — for readable text labels */
  text: string;
}

/**
 * Derives all display tokens from a single CSS color value.
 *
 * Hex colors (`#rrggbb`, `#rgb`) are expanded to `rgba()` for the
 * opacity variants — this works in every browser. Any other CSS color
 * format (hsl, oklch, named colors, …) falls back to `color-mix()`,
 * which is supported in Chrome 111+, Firefox 113+, and Safari 16.2+.
 *
 * @example
 * const tokens = getStateTokens('#60a5fa')
 * // { dot: '#60a5fa', background: 'rgba(96, 165, 250, 0.1)', ... }
 *
 * @example
 * // In JSX
 * const tokens = getStateTokens(skin.board.stateColors['SCREENING'])
 * <span style={{ color: tokens.dot }}>●</span>
 * <div style={{ backgroundColor: tokens.background, borderColor: tokens.border }}>
 */
export function getStateTokens(color: string): StateDisplayTokens {
  if (color.startsWith('#')) {
    const rgb = parseHexColor(color);
    if (rgb) {
      return {
        dot: color,
        background: `rgba(${rgb}, 0.1)`,
        border: `rgba(${rgb}, 0.2)`,
        text: color,
      };
    }
  }

  // Fallback for hsl(), rgb(), oklch(), or named colors
  return {
    dot: color,
    background: `color-mix(in srgb, ${color} 10%, transparent)`,
    border: `color-mix(in srgb, ${color} 20%, transparent)`,
    text: color,
  };
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Parses a CSS hex color string into an "r, g, b" string suitable for
 * inserting into an rgba() call. Returns null for unrecognised formats.
 *
 * Supports 3-digit shorthand (#rgb → expanded to #rrggbb).
 */
function parseHexColor(hex: string): string | null {
  const raw = hex.replace('#', '');

  const expanded =
    raw.length === 3
      ? raw.split('').map(ch => ch + ch).join('')
      : raw;

  if (expanded.length !== 6) return null;

  const r = parseInt(expanded.slice(0, 2), 16);
  const g = parseInt(expanded.slice(2, 4), 16);
  const b = parseInt(expanded.slice(4, 6), 16);

  if (isNaN(r) || isNaN(g) || isNaN(b)) return null;

  return `${r}, ${g}, ${b}`;
}
