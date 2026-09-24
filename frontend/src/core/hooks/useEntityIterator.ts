import { useCallback, useState } from 'react';

/**
 * Navigation contract for an ordered entity collection.
 * `current` is the 1-based position, `total` is the collection size, callbacks
 * move one entity in either direction, and `disabled` temporarily locks both.
 */
export interface EntityIteratorState {
  current: number;
  total: number;
  onPrevious: () => void;
  onNext: () => void;
  disabled?: boolean;
}

/** Render-ready label, visibility, and boundary states for iterator controls. */
export interface EntityIteratorViewState {
  hidden: boolean;
  label: string;
  previousDisabled: boolean;
  nextDisabled: boolean;
}

/** Derives the visible counter and explicit boundary states for the controls. */
export function entityIteratorViewState(
  current: number,
  total: number,
  disabled: boolean,
): EntityIteratorViewState {
  return {
    hidden: total <= 0 || current <= 0,
    label: `${current} of ${total}`,
    previousDisabled: disabled || current <= 1,
    nextDisabled: disabled || current >= total,
  };
}

/**
 * Resolves the Alt+Arrow keyboard shortcut to an iterator offset while
 * respecting disabled and boundary states.
 */
export function entityIteratorDirectionForKey(
  key: string,
  altKey: boolean,
  current: number,
  total: number,
  disabled: boolean,
): -1 | 1 | null {
  if (!altKey || disabled || current <= 0 || total <= 0) return null;
  if (key === 'ArrowLeft' && current > 1) return -1;
  if (key === 'ArrowRight' && current < total) return 1;
  return null;
}

/**
 * Tracks whether the currently displayed entity has entered inline edit mode.
 * Consumers use `clearEditing` when their detail surface closes.
 */
export function useEntityEditingLock(entityId: string | undefined): {
  editing: boolean;
  onEditingChange: (editing: boolean) => void;
  clearEditing: () => void;
} {
  const [editingEntityId, setEditingEntityId] = useState<string | null>(null);
  const onEditingChange = useCallback(
    (editing: boolean) => setEditingEntityId(editing ? entityId ?? null : null),
    [entityId],
  );
  const clearEditing = useCallback(() => setEditingEntityId(null), []);

  return {
    editing: Boolean(entityId && editingEntityId === entityId),
    onEditingChange,
    clearEditing,
  };
}
