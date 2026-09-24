/**
 * ColorSwatchPicker
 *
 * A palette of preset swatches plus a "custom" swatch backed by the native
 * color input, for any single hex-color setting. Extracted from the Roles
 * "Role color" picker (settings/components/role/detail/display-tab.tsx) so
 * every other place needing a color setting — a field's background/text
 * color, a table column's, anything future — reuses this instead of a new
 * one-off picker. Roles keep using it via this component; behavior there is
 * unchanged.
 */

import { Check } from 'lucide-react';
import { COLOR_PALETTE } from '@/lib/roles-data';

/** What a colour setting falls back to before anything is picked. Shared so
 *  the field editor and the table column editor cannot drift apart. */
export const DEFAULT_BACKGROUND_COLOR = '#ffffff';
export const DEFAULT_TEXT_COLOR = '#000000';

interface ColorSwatchPickerProps {
  value: string;
  onChange: (hex: string) => void;
  disabled?: boolean;
  /** Defaults to the same palette Roles uses. */
  palette?: string[];
  /** Swatch side length in px. Defaults to the Roles picker's size. */
  size?: number;
}

export default function ColorSwatchPicker({
  value,
  onChange,
  disabled = false,
  palette = COLOR_PALETTE,
  size = 34,
}: ColorSwatchPickerProps) {
  const normalized = value.toUpperCase();
  const isPreset = palette.some((c) => c.toUpperCase() === normalized);
  const dim = `${size}px`;

  return (
    <div className="flex flex-wrap gap-[10px]">
      {palette.map((c) => {
        const selected = c.toUpperCase() === normalized;
        return (
          <button
            key={c}
            type="button"
            onClick={() => onChange(c)}
            disabled={disabled}
            className="rounded-[9px] border-none cursor-pointer flex items-center justify-center text-white transition-transform hover:scale-[1.08] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:scale-100"
            style={{
              width: dim,
              height: dim,
              backgroundColor: c,
              boxShadow: selected ? `0 0 0 2px var(--card), 0 0 0 4px ${c}` : 'none',
            }}
          >
            {selected && <Check width={size * 0.5} height={size * 0.5} strokeWidth={2.4} />}
          </button>
        );
      })}
      {/* Custom color — native color input, swatch shows the picked value once it's off-palette. */}
      <div className="relative" style={{ width: dim, height: dim }}>
        <input
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className="absolute inset-0 h-full w-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
        />
        <div
          className="flex h-full w-full items-center justify-center overflow-hidden rounded-[9px] border-2 border-dashed border-border transition-colors hover:border-muted-foreground"
          style={{
            background: isPreset
              ? 'linear-gradient(135deg, #FF6B6B 0%, #4ECDC4 25%, #45B7D1 50%, #96E6A1 75%, #DDA0DD 100%)'
              : value,
          }}
        >
          {isPreset ? (
            <span className="text-[11px] font-bold text-muted-foreground">+</span>
          ) : (
            <Check width={size * 0.5} height={size * 0.5} strokeWidth={2.4} className="text-white drop-shadow-sm" />
          )}
        </div>
      </div>
    </div>
  );
}
