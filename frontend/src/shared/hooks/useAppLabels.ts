import { useMemo } from 'react';

import { useAuth } from '@/core/auth';

/**
 * Renameable main-app section labels. One key per section; the value drives the
 * sidebar nav, breadcrumb, and page heading for that section together.
 * Keys mirror the route slugs (`/dashboard` -> `dashboard`).
 */
export interface AppLabels {
  dashboard: string;
  workflows: string;
  records: string;
  pipeline: string;
}

const DEFAULTS: AppLabels = {
  dashboard: 'Dashboard',
  workflows: 'Workflows',
  records: 'Records',
  pipeline: 'Pipeline',
};

/** Order + default metadata for the app-labels editor (Settings). */
export const APP_LABEL_FIELDS: { key: keyof AppLabels; defaultLabel: string }[] = [
  { key: 'dashboard', defaultLabel: DEFAULTS.dashboard },
  { key: 'workflows', defaultLabel: DEFAULTS.workflows },
  { key: 'records', defaultLabel: DEFAULTS.records },
  { key: 'pipeline', defaultLabel: DEFAULTS.pipeline },
];

export const APP_LABEL_DEFAULTS = DEFAULTS;

/**
 * Resolves the main-app section labels, overridable per organization via
 * `organization.settings.appLabels` (a free-form JSON blob, no migration —
 * same storage as `columnLabels`). Empty/missing overrides fall back to the
 * built-in defaults, so existing orgs keep the current names.
 */
export function useAppLabels(): AppLabels {
  const { organization } = useAuth();
  return useMemo(() => {
    const overrides =
      (organization?.settings?.appLabels as Partial<AppLabels> | undefined) ?? {};
    return {
      dashboard: overrides.dashboard || DEFAULTS.dashboard,
      workflows: overrides.workflows || DEFAULTS.workflows,
      records: overrides.records || DEFAULTS.records,
      pipeline: overrides.pipeline || DEFAULTS.pipeline,
    };
  }, [organization?.settings]);
}
