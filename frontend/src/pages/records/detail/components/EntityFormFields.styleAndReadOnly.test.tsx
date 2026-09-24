/**
 * Proves two things end to end through the real render path (not just the
 * settings UI): a textarea field's `style_config` reaches the actual control
 * as inline color styles, and `read_only` disables it independent of RBAC
 * field permissions — while leaving `canEditField` (permission) able to
 * allow editing on its own, showing the two are ANDed rather than one
 * replacing the other.
 */

import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { FormField } from '@/core/types';
import EntityFormFields from './EntityFormFields';

// This project's vitest config runs without RTL's auto-cleanup wired up, so
// each render's DOM would otherwise pile up across tests in this file.
afterEach(cleanup);

// canEditField always true here — isolates the assertion to field.read_only,
// proving read_only disables the field even when permissions would allow it.
vi.mock('@/core/hooks/usePermissions', () => ({
  usePermissions: () => ({
    canViewField: () => true,
    canEditField: () => true,
    shouldMaskField: () => false,
  }),
}));

const STYLED_FIELD: FormField = {
  id: 'notes',
  label: 'Styled Notes',
  type: 'textarea',
  required: false,
  system: false,
  style_config: { background_color: '#EA580C', text_color: '#16A34A' },
};

const READ_ONLY_FIELD: FormField = {
  id: 'locked_notes',
  label: 'Locked Notes',
  type: 'textarea',
  required: false,
  system: false,
  read_only: true,
};

const EDITABLE_FIELD: FormField = {
  id: 'plain_notes',
  label: 'Plain Notes',
  type: 'textarea',
  required: false,
  system: false,
};

describe('EntityFormFields — textarea style_config and read_only', () => {
  it('renders the configured background and text color on the actual control', () => {
    const { container } = render(
      <EntityFormFields
        fields={[STYLED_FIELD]}
        values={{ notes: '' }}
        onChange={vi.fn()}
        entityType="E2EBaseline"
        mode="edit"
      />,
    );
    // RichTextEditor's outer container carries the background color.
    const styled = container.querySelector('[style*="background-color"]') as HTMLElement | null;
    expect(styled).not.toBeNull();
    expect(styled!.style.backgroundColor).toBe('rgb(234, 88, 12)'); // #EA580C
    // The write-mode textarea carries the text color. Empty value keeps the
    // editor in Write mode (non-empty content flips it to Preview by default).
    const textarea = container.querySelector('textarea') as HTMLTextAreaElement | null;
    expect(textarea).not.toBeNull();
    expect(textarea!.style.color).toBe('rgb(22, 163, 74)'); // #16A34A
  });

  it('disables the field when read_only is set, even though canEditField allows it', () => {
    const { container } = render(
      <EntityFormFields
        fields={[READ_ONLY_FIELD]}
        values={{ locked_notes: '' }}
        onChange={vi.fn()}
        entityType="E2EBaseline"
        mode="edit"
      />,
    );
    const textarea = container.querySelector('textarea') as HTMLTextAreaElement;
    expect(textarea.disabled).toBe(true);
  });

  it('leaves an ordinary field editable — read_only is opt-in, not a new default', () => {
    const { container } = render(
      <EntityFormFields
        fields={[EDITABLE_FIELD]}
        values={{ plain_notes: '' }}
        onChange={vi.fn()}
        entityType="E2EBaseline"
        mode="edit"
      />,
    );
    const textarea = container.querySelector('textarea') as HTMLTextAreaElement;
    expect(textarea.disabled).toBe(false);
  });

  it('view mode still disables regardless of read_only (existing behavior unchanged)', () => {
    const { container } = render(
      <EntityFormFields
        fields={[EDITABLE_FIELD]}
        values={{ plain_notes: '' }}
        onChange={vi.fn()}
        entityType="E2EBaseline"
        mode="view"
      />,
    );
    const textarea = container.querySelector('textarea') as HTMLTextAreaElement;
    expect(textarea.disabled).toBe(true);
  });
});
