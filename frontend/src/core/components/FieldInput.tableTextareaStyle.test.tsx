/**
 * Proves a Table/Grid field's textarea column applies its own
 * `style_config` to the actual per-row `<textarea>` cell — the "same color
 * settings apply to a text-area column inside a Table/Grid field"
 * requirement, exercised through the real render path.
 */

import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { FormField } from '@/core/types';
import FieldInput from './FieldInput';

afterEach(cleanup);

const TABLE_FIELD: FormField = {
  id: 'line_items',
  label: 'Line Items',
  type: 'table',
  required: false,
  system: false,
  table_config: {
    row_mode: 'dynamic',
    display_mode: 'form',
    columns: [
      {
        id: 'notes',
        label: 'Notes',
        type: 'textarea',
        style_config: { background_color: '#EA580C', text_color: '#16A34A' },
      },
    ],
  },
};

describe('FieldInput — table field textarea column style_config', () => {
  it('applies the column style_config to the rendered cell textarea', () => {
    const { container } = render(
      <FieldInput
        field={TABLE_FIELD}
        value={[{ _row_id: 'r1', notes: '' }]}
        onChange={vi.fn()}
      />,
    );
    const textarea = container.querySelector('textarea') as HTMLTextAreaElement | null;
    expect(textarea).not.toBeNull();
    expect(textarea!.style.backgroundColor).toBe('rgb(234, 88, 12)'); // #EA580C
    expect(textarea!.style.color).toBe('rgb(22, 163, 74)'); // #16A34A
  });
});
