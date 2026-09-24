import type { WorkflowEntityState } from '../../../core/services/api';
import type { FormSchema, StateMachineRecord } from '../../../core/types';
import { getFormFields } from '../../../shared/utils/entityForm';
import { resolveEntityTypeLabel } from '../../../shared/utils/labels';

export function formatDate(iso?: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function normalizeEntityType(value: string): string {
  return value.replace(/^ATS\./i, '').trim().toLowerCase();
}

/** Compares the editable draft with the entity data used to seed it. */
export function isEntityEditDirty(
  draft: Record<string, unknown>,
  original: Record<string, unknown>,
): boolean {
  return JSON.stringify(draft) !== JSON.stringify(original);
}

export function displayEntityType(value: string): string {
  return resolveEntityTypeLabel(value);
}

export function pluralizeEntityType(value: string): string {
  if (!value) return 'Entities';
  if (value.endsWith('s')) return value;
  return `${value}s`;
}

export function isSchemaForMachineEntityType(
  schema: FormSchema,
  machine: StateMachineRecord,
): boolean {
  const schemaType = normalizeEntityType(schema.entity_type);
  return (
    schemaType === normalizeEntityType(machine.entity_type) ||
    schemaType === normalizeEntityType(machine.machine_name)
  );
}

export function dedupeMachinesByName(machines: StateMachineRecord[]): StateMachineRecord[] {
  const byName = new Map<string, StateMachineRecord>();
  for (const machine of machines) {
    const existing = byName.get(machine.machine_name);
    if (!existing) {
      byName.set(machine.machine_name, machine);
      continue;
    }
    // Prefer the active version. If both have the same active status, prefer the higher version.
    if (!existing.is_active && machine.is_active) {
      byName.set(machine.machine_name, machine);
    } else if (existing.is_active === machine.is_active && machine.version > existing.version) {
      byName.set(machine.machine_name, machine);
    }
  }
  return Array.from(byName.values());
}

export function deriveEntityDisplayName(
  entity: WorkflowEntityState,
  schema: FormSchema | null,
): string {
  if (entity.display_name?.trim()) return entity.display_name.trim();
  const fields = getFormFields(schema);
  for (const field of fields) {
    const value = entity.data[field.id];
    if (typeof value === 'string' && value.trim()) return value.trim();
    if (Array.isArray(value) && value.length > 0) return value.join(', ');
    if (value !== null && value !== undefined && value !== '') return String(value);
  }
  const values = Object.values(entity.data);
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim();
    if (Array.isArray(value) && value.length > 0) return value.join(', ');
    if (value !== null && value !== undefined && value !== '') return String(value);
  }
  return entity.entity_id.slice(0, 8);
}
