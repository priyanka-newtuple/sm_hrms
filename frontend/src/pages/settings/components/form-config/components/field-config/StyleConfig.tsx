/**
 * Generic per-type appearance override — background and text color — stored
 * on `field.style_config`. Mounted per type in `FieldTypeConfig`, currently
 * for `textarea` only, but the setting itself isn't type-specific: any type
 * whose renderer reads `style_config` can opt in the same way.
 *
 * Reuses the same swatch-palette + custom-color picker as the Roles "Role
 * color" setting, rather than a one-off input, so any future color setting
 * looks and behaves the same way.
 */

import type { FormField } from '@/core/types';
import ColorSwatchPicker, {
  DEFAULT_BACKGROUND_COLOR,
  DEFAULT_TEXT_COLOR,
} from '@/core/components/ColorSwatchPicker';
import { CONFIG_LABEL_CLASS, CONFIG_PANEL_CLASS } from './styles';

type StyleConfigProps = {
  field: FormField;
  canWrite: boolean;
  onChange: (patch: Partial<FormField>) => void;
};

export default function StyleConfig({ field, canWrite, onChange }: StyleConfigProps) {
  const config = field.style_config ?? {};

  const setColor = (key: 'background_color' | 'text_color', value: string) => {
    onChange({ style_config: { ...config, [key]: value } });
  };

  return (
    <div className={CONFIG_PANEL_CLASS}>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={CONFIG_LABEL_CLASS}>Background color</label>
          <ColorSwatchPicker
            value={config.background_color ?? DEFAULT_BACKGROUND_COLOR}
            onChange={(hex) => setColor('background_color', hex)}
            disabled={!canWrite}
            size={26}
          />
        </div>
        <div>
          <label className={CONFIG_LABEL_CLASS}>Text color</label>
          <ColorSwatchPicker
            value={config.text_color ?? DEFAULT_TEXT_COLOR}
            onChange={(hex) => setColor('text_color', hex)}
            disabled={!canWrite}
            size={26}
          />
        </div>
      </div>
      {(config.background_color || config.text_color) && (
        <button
          type="button"
          onClick={() => onChange({ style_config: undefined })}
          disabled={!canWrite}
          className="mt-2 text-xs text-muted-foreground hover:text-foreground hover:underline disabled:opacity-60"
        >
          Reset to default colors
        </button>
      )}
    </div>
  );
}
