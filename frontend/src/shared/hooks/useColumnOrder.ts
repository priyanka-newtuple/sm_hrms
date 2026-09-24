import { useCallback, useMemo } from 'react';
import { useAuth } from '@/core/auth';
import { organizations } from '@/core/services/api';

/**
 * Org-wide column ordering, persisted in the organization settings JSON blob
 * (`organization.settings.columnOrder`) — no migration, shared across users.
 * Returns the saved order plus a setter that writes through to the org and
 * refreshes the auth context so the change applies live everywhere.
 */
export function useColumnOrder(): {
  order: string[];
  setOrder: (ids: string[]) => Promise<void>;
} {
  const { organization, refreshOrganization } = useAuth();

  const order = useMemo(() => {
    const raw = organization?.settings?.columnOrder;
    return Array.isArray(raw) ? (raw.filter((x) => typeof x === 'string') as string[]) : [];
  }, [organization?.settings]);

  const setOrder = useCallback(
    async (ids: string[]) => {
      await organizations.updateBranding({ settings: { columnOrder: ids } });
      await refreshOrganization();
    },
    [refreshOrganization],
  );

  return { order, setOrder };
}

/**
 * Reorder `ids` so entries present in `savedOrder` come first (in that order),
 * with any remaining ids kept in their original relative order. New columns
 * that the saved order doesn't know about are appended, never dropped.
 */
export function applyColumnOrder(ids: string[], savedOrder: string[]): string[] {
  if (savedOrder.length === 0) return ids;
  const known = new Set(ids);
  const ranked = savedOrder.filter((id) => known.has(id));
  const rankedSet = new Set(ranked);
  const rest = ids.filter((id) => !rankedSet.has(id));
  return [...ranked, ...rest];
}
