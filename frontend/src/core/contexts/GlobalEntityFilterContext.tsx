import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import { useAuth } from '../auth';
import { request } from '../services/api/client';

export interface GlobalEntityFilterSettings {
  enabled: boolean;
  anchorEntityType: string | null;
  placement: 'left' | 'right';
}

interface GlobalEntityFilterContextValue {
  settings: GlobalEntityFilterSettings;
  activeAnchorEntityId: string | null;
  activeAnchorLabel: string;
  setActiveAnchor: (entityId: string, label: string) => void;
  clearActiveAnchor: () => void;
}

const DEFAULT_SETTINGS: GlobalEntityFilterSettings = {
  enabled: false,
  anchorEntityType: null,
  placement: 'right',
};

const GlobalEntityFilterContext = createContext<GlobalEntityFilterContextValue | null>(null);

/**
 * Parse global entity filter settings from an organization's settings blob.
 * Returns disabled defaults when the setting is absent or malformed.
 */
export function globalEntityFilterSettingsFromOrg(
  settings: Record<string, unknown> | undefined,
): GlobalEntityFilterSettings {
  const raw = settings?.globalEntityFilter;
  if (!raw || typeof raw !== 'object') return DEFAULT_SETTINGS;
  const record = raw as Record<string, unknown>;
  const anchorEntityType =
    typeof record.anchorEntityType === 'string' && record.anchorEntityType.trim()
      ? record.anchorEntityType.trim()
      : null;
  return {
    enabled: Boolean(record.enabled),
    anchorEntityType,
    placement: record.placement === 'left' ? 'left' : 'right',
  };
}

function storageKey(organizationId: string | undefined, anchorEntityType: string | null): string {
  return `global-entity-filter:${organizationId ?? 'none'}:${anchorEntityType ?? 'none'}`;
}

/**
 * Provides org-level global entity filter settings and session-scoped anchor state.
 */
export function GlobalEntityFilterProvider({ children }: { children: ReactNode }) {
  const { organization } = useAuth();
  const settings = useMemo(
    () => globalEntityFilterSettingsFromOrg(organization?.settings),
    [organization?.settings],
  );
  const key = storageKey(organization?.id, settings.anchorEntityType);
  const [activeAnchorEntityId, setActiveAnchorEntityId] = useState<string | null>(null);
  const [activeAnchorLabel, setActiveAnchorLabel] = useState('');

  useEffect(() => {
    if (!settings.enabled || !settings.anchorEntityType) {
      setActiveAnchorEntityId(null);
      setActiveAnchorLabel('');
      return;
    }
    let saved: { entityId?: string; label?: string } = {};
    try {
      saved = JSON.parse(window.sessionStorage.getItem(key) || '{}');
    } catch (error) {
      console.warn('Failed to parse global entity filter session data:', error);
    }
    const entityId = saved.entityId || null;
    if (!entityId) {
      setActiveAnchorEntityId(null);
      setActiveAnchorLabel('');
      return;
    }
    // A persisted anchor that has since been deleted or archived makes every
    // anchored request (enrollments, record summaries, dashboards) 404, and the
    // stale id outlives the entity. Verify once on restore and drop it if gone.
    let cancelled = false;
    request(`/entity-records/${encodeURIComponent(entityId)}`).then(
      () => {
        if (cancelled) return;
        setActiveAnchorEntityId(entityId);
        setActiveAnchorLabel(saved.label || '');
      },
      (error) => {
        if (cancelled) return;
        console.warn('Dropping stale global entity filter anchor:', entityId, error);
        window.sessionStorage.removeItem(key);
        setActiveAnchorEntityId(null);
        setActiveAnchorLabel('');
      },
    );
    return () => {
      cancelled = true;
    };
  }, [key, settings.enabled, settings.anchorEntityType]);

  const value = useMemo<GlobalEntityFilterContextValue>(
    () => ({
      settings,
      activeAnchorEntityId,
      activeAnchorLabel,
      setActiveAnchor: (entityId, label) => {
        setActiveAnchorEntityId(entityId);
        setActiveAnchorLabel(label);
        window.sessionStorage.setItem(key, JSON.stringify({ entityId, label }));
      },
      clearActiveAnchor: () => {
        setActiveAnchorEntityId(null);
        setActiveAnchorLabel('');
        window.sessionStorage.removeItem(key);
      },
    }),
    [activeAnchorEntityId, activeAnchorLabel, key, settings],
  );

  return (
    <GlobalEntityFilterContext.Provider value={value}>
      {children}
    </GlobalEntityFilterContext.Provider>
  );
}

/**
 * Reads and updates the active global entity filter anchor.
 * Throws when used outside GlobalEntityFilterProvider.
 */
export function useGlobalEntityFilter(): GlobalEntityFilterContextValue {
  const context = useContext(GlobalEntityFilterContext);
  if (!context) {
    throw new Error('useGlobalEntityFilter must be used within GlobalEntityFilterProvider');
  }
  return context;
}
