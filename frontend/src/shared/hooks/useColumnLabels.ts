import { useMemo } from 'react';
import { useAuth } from '@/core/auth';

export interface ColumnLabels {
  entity: string;
  identifier: string;
  state: string;
  created: string;
  workflow: string;
  owner: string;
}

const DEFAULTS: ColumnLabels = {
  entity: 'Name',
  identifier: 'Unique Name',
  state: 'Status',
  created: 'Created',
  workflow: 'Workflow',
  owner: 'Owner',
};

/** Order + display metadata for the column-labels editor (Settings). */
export const COLUMN_LABEL_FIELDS: { key: keyof ColumnLabels; defaultLabel: string }[] = [
  { key: 'entity', defaultLabel: DEFAULTS.entity },
  { key: 'identifier', defaultLabel: DEFAULTS.identifier },
  { key: 'workflow', defaultLabel: DEFAULTS.workflow },
  { key: 'owner', defaultLabel: DEFAULTS.owner },
  { key: 'state', defaultLabel: DEFAULTS.state },
  { key: 'created', defaultLabel: DEFAULTS.created },
];

export const COLUMN_LABEL_DEFAULTS = DEFAULTS;

/**
 * Resolves list column-header labels, overridable per organization via
 * `organization.settings.columnLabels` (a free-form JSON blob, no migration).
 * Falls back to friendlier defaults than the raw technical names.
 */
export function useColumnLabels(): ColumnLabels {
  const { organization } = useAuth();
  return useMemo(() => {
    const overrides =
      (organization?.settings?.columnLabels as Partial<ColumnLabels> | undefined) ?? {};
    return {
      entity: overrides.entity || DEFAULTS.entity,
      identifier: overrides.identifier || DEFAULTS.identifier,
      state: overrides.state || DEFAULTS.state,
      created: overrides.created || DEFAULTS.created,
      workflow: overrides.workflow || DEFAULTS.workflow,
      owner: overrides.owner || DEFAULTS.owner,
    };
  }, [organization?.settings]);
}
