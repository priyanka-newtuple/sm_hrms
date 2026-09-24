/**
 * Workflow-list refresh announcement on save.
 *
 * The workflow list is fetched once into a shared cache that only refetches
 * when a `state-machines-changed` event tells it to. Publishing always fired
 * that event; saving a draft did not, so Settings -> Funnels kept serving
 * pre-save data until the cache aged out. These guard that both save paths
 * announce, and that a failed save stays silent.
 */
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { StateMachineRecord } from '@/core/types';

const { seedDraft, saveDraftApi, publishApi, refreshPermissions } = vi.hoisted(() => ({
  seedDraft: vi.fn(),
  saveDraftApi: vi.fn(),
  publishApi: vi.fn(),
  refreshPermissions: vi.fn(),
}));

vi.mock('@/core/auth', () => ({
  useAuth: () => ({ refreshPermissions }),
}));

vi.mock('@/core/services/api', () => ({
  default: {
    stateMachines: { seedDraft, saveDraft: saveDraftApi, publish: publishApi },
  },
}));

const { useStateMachineDoc } = await import('./useStateMachineDoc');

// Deliberately the literal, not STATE_MACHINES_CHANGED_EVENT: listeners depend
// on this exact string, so changing the constant's value should fail here.
const EVENT = 'state-machines-changed';

function record(overrides: Partial<StateMachineRecord> = {}): StateMachineRecord {
  return {
    id: 'draft-row-1',
    machine_key: 'wf_under_test',
    machine_name: 'wf_under_test',
    name: 'Workflow Under Test',
    entity_type: 'patient',
    version: 0,
    is_active: false,
    definition: { states: [], transitions: [] },
    organization_id: 'org-1',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('useStateMachineDoc save paths', () => {
  let listener: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    listener = vi.fn();
    window.addEventListener(EVENT, listener);
    seedDraft.mockResolvedValue(record());
  });

  afterEach(() => {
    window.removeEventListener(EVENT, listener);
  });

  it('announces a list change after a draft is saved', async () => {
    saveDraftApi.mockResolvedValue({
      record: record({ name: 'Renamed In Draft' }),
      validation_issues: [],
      is_valid: true,
      deactivated: false,
    });

    const { result } = renderHook(() => useStateMachineDoc({}));
    await act(async () => {
      await result.current.saveDraft();
    });

    expect(saveDraftApi).toHaveBeenCalledTimes(1);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('announces even when the draft saved with validation issues', async () => {
    // A draft that fails validation is auto-deactivated, which changes what the
    // Funnels list shows — so this case has to refresh too.
    saveDraftApi.mockResolvedValue({
      record: record(),
      validation_issues: [{ code: 'x', message: 'bad', severity: 'error' }],
      is_valid: false,
      deactivated: true,
    });

    const { result } = renderHook(() => useStateMachineDoc({}));
    await act(async () => {
      await result.current.saveDraft();
    });

    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('stays silent when the draft save fails', async () => {
    saveDraftApi.mockRejectedValue(new Error('save exploded'));

    const { result } = renderHook(() => useStateMachineDoc({}));
    await act(async () => {
      await result.current.saveDraft();
    });

    expect(result.current.draftError).toBe('save exploded');
    expect(listener).not.toHaveBeenCalled();
  });

  it('still announces after a publish', async () => {
    publishApi.mockResolvedValue({
      state_machine: record({ version: 1, is_active: true }),
    });

    const { result } = renderHook(() => useStateMachineDoc({}));
    await act(async () => {
      await result.current.save();
    });

    expect(listener).toHaveBeenCalledTimes(1);
  });
});
