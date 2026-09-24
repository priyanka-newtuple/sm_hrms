/**
 * Shared constants for the role editor wizard.
 */

import type { PermissionAction } from '../../../../core/types';

export const ACTIONS: { key: PermissionAction; label: string }[] = [
  { key: 'view', label: 'View' },
  { key: 'create', label: 'Create' },
  { key: 'edit', label: 'Edit' },
  { key: 'delete', label: 'Delete' },
  { key: 'transition', label: 'Transition' },
];

export type WizardStep = 'basics' | 'entity' | 'fields';

export const WIZARD_STEPS: { key: WizardStep; label: string }[] = [
  { key: 'basics', label: 'Basics' },
  { key: 'entity', label: 'Entity Permissions' },
  { key: 'fields', label: 'Field Permissions' },
];
