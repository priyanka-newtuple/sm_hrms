import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { FilterBarItem } from '@/skins';
import type { WorkflowEntityState } from '@/core/services/api';
import { useAuth } from '@/core/auth';

const PARAM_PREFIX = 'filter_';
const DATERANGE_PRESET_DAYS: Record<string, number> = { today: 1, '7d': 7, '30d': 30, '90d': 90 };
const EMPTY_FILTER_VALUES: Record<string, string> = {};
/** Shared with BoardFilterBar's "Assigned to me" option — keep both in sync. */
export const ASSIGNEE_FILTER_VALUE_MINE = 'mine';

/**
 * Manages skin-driven board filter state in URL search params so filters survive
 * navigation and are deep-linkable. Filter values are keyed as `filter_<key>`.
 */
export function useBoardFilters(filterConfig: FilterBarItem[]): {
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
  applyTo: (entities: WorkflowEntityState[]) => WorkflowEntityState[];
} {
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();

  const values = useMemo(() => {
    if (filterConfig.length === 0) return EMPTY_FILTER_VALUES;
    const result: Record<string, string> = {};
    for (const f of filterConfig) {
      result[f.key] = searchParams.get(`${PARAM_PREFIX}${f.key}`) ?? '';
    }
    return result;
  }, [filterConfig, searchParams]);

  const onChange = useCallback(
    (key: string, value: string) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (value) next.set(`${PARAM_PREFIX}${key}`, value);
          else next.delete(`${PARAM_PREFIX}${key}`);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const applyTo = useCallback(
    (entities: WorkflowEntityState[]): WorkflowEntityState[] => {
      const active = filterConfig.filter((f) => values[f.key]);
      if (!active.length) return entities;
      return entities.filter((entity) =>
        active.every((f) => {
          const filterValue = values[f.key].toLowerCase();

          if (f.type === 'assignee') {
            if (filterValue !== ASSIGNEE_FILTER_VALUE_MINE) return true;
            return Boolean(user?.id) && entity.assignee_id === user?.id;
          }

          if (f.type === 'daterange') {
            const days = DATERANGE_PRESET_DAYS[filterValue];
            if (!days) return true;
            const raw = entity.data?.[f.key] ?? entity.created_at;
            const ts = raw ? new Date(String(raw)).getTime() : NaN;
            if (!Number.isFinite(ts)) return false;
            return Date.now() - ts <= days * 24 * 60 * 60 * 1000;
          }

          const raw = entity.data?.[f.key];
          const entityValue = String(raw ?? '').toLowerCase();
          if (f.type === 'search') return entityValue.includes(filterValue);
          if (f.type === 'select') return entityValue === filterValue;
          return true;
        }),
      );
    },
    [filterConfig, values, user?.id],
  );

  return { values, onChange, applyTo };
}
