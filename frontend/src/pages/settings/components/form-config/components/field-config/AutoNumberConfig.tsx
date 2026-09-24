/**
 * The affix of an `auto_number` field: the backend generates the number, this
 * only decides what is printed around it.
 */

import type { FormField } from '@/core/types';
import { CONFIG_INPUT_CLASS, CONFIG_LABEL_CLASS, CONFIG_PANEL_CLASS } from './styles';

type AutoNumberConfigProps = {
  field: FormField;
  canWrite: boolean;
  onChange: (patch: Partial<FormField>) => void;
};

const AFFIX_MODES = [
  { value: 'none', label: 'None (ID only)' },
  { value: 'prefix', label: 'Prefix' },
  { value: 'suffix', label: 'Suffix' },
] as const;

export default function AutoNumberConfig({ field, canWrite, onChange }: AutoNumberConfigProps) {
  const config = field.auto_number_config ?? {};

  return (
    <div className={CONFIG_PANEL_CLASS}>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={CONFIG_LABEL_CLASS}>Affix position</label>
          <select
            value={config.affix_mode ?? 'none'}
            onChange={(event) =>
              onChange({
                auto_number_config: {
                  ...config,
                  affix_mode: event.target.value as 'none' | 'prefix' | 'suffix',
                },
              })
            }
            disabled={!canWrite}
            className={CONFIG_INPUT_CLASS}
          >
            {AFFIX_MODES.map((mode) => (
              <option key={mode.value} value={mode.value}>{mode.label}</option>
            ))}
          </select>
        </div>
        {config.affix_mode && config.affix_mode !== 'none' && (
          <div>
            <label className={CONFIG_LABEL_CLASS}>Affix text</label>
            <input
              type="text"
              maxLength={64}
              value={config.affix ?? ''}
              onChange={(event) => onChange({ auto_number_config: { ...config, affix: event.target.value } })}
              placeholder="e.g., jb"
              disabled={!canWrite}
              className={CONFIG_INPUT_CLASS}
            />
          </div>
        )}
      </div>
    </div>
  );
}
