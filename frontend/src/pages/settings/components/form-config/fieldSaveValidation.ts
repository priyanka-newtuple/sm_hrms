import type { FormField, Picklist } from '../../../../core/types';
import { WIZARD_COPY_KEYS, clearedWizardCopy } from '../../../../core/types/wizardCopy';
import { EXTENSION_DISALLOWED_TYPES, FIELD_TYPE_LABELS } from './constants';

function picklistOptions(options: Picklist['options']): { enum_values: string[]; enum_labels: string[] } {
  return {
    enum_values: options.map((option) => option.value),
    enum_labels: options.map((option) => option.label),
  };
}

/**
 * Drop "Extend Field" configuration that can no longer apply.
 *
 * Options are pruned when the second picklist no longer offers them (it was
 * edited or swapped after the extensions were configured) and when they
 * configure no fields, so an option that reveals nothing is stored as nothing.
 * Returns `undefined` once nothing is left, which is what turns Extend Field
 * back off rather than leaving an empty husk behind.
 */
function pruneExtensions(
  extensions: FormField['extensions'],
  optionValues: string[],
): FormField['extensions'] | undefined {
  if (!extensions) return undefined;
  const allowed = new Set(optionValues);
  const pruned: NonNullable<FormField['extensions']> = {};
  for (const [option, entry] of Object.entries(extensions)) {
    if (!allowed.has(option) || entry.fields.length === 0) continue;
    pruned[option] = entry;
  }
  return Object.keys(pruned).length > 0 ? pruned : undefined;
}

/** The first disallowed extension field type in use, or null when all are fine. */
function disallowedExtensionType(extensions: FormField['extensions']): string | null {
  for (const entry of Object.values(extensions ?? {})) {
    const offender = entry.fields.find((field) => EXTENSION_DISALLOWED_TYPES.includes(field.type));
    if (offender) return FIELD_TYPE_LABELS[offender.type] ?? offender.type;
  }
  return null;
}

/**
 * Resolve and validate a field immediately before persistence.
 *
 * Both Forms and the Field Library use this function so their picklist
 * snapshots and per-type validation rules stay identical.
 */
export function resolveFieldForSave(
  field: FormField,
  picklists: Picklist[],
): { resolved: FormField; error: string | null } {
  let resolved = { ...field };

  if (
    (resolved.type === 'select' || resolved.type === 'multi_select') &&
    resolved.picklist_id
  ) {
    const picklist = picklists.find((candidate) => candidate.id === resolved.picklist_id);
    if (!picklist) return { resolved, error: 'Selected picklist was not found' };
    resolved = { ...resolved, ...picklistOptions(picklist.options) };
  }

  if (resolved.type === 'picklist_multi') {
    if (resolved.picklist_id) {
      const firstPicklist = picklists.find((candidate) => candidate.id === resolved.picklist_id);
      if (firstPicklist) resolved = { ...resolved, ...picklistOptions(firstPicklist.options) };
    }
    if (resolved.picklist_id_2) {
      const secondPicklist = picklists.find((candidate) => candidate.id === resolved.picklist_id_2);
      if (secondPicklist) {
        resolved = {
          ...resolved,
          enum_values_2: secondPicklist.options.map((option) => option.value),
          enum_labels_2: secondPicklist.options.map((option) => option.label),
        };
      }
    }
    const prunedExtensions = pruneExtensions(resolved.extensions, resolved.enum_values_2 ?? []);
    resolved = {
      ...resolved,
      extensions: prunedExtensions,
      // Nothing left to label once every option has been pruned away.
      ...(prunedExtensions ? {} : { extension_label: undefined }),
    };
  } else if (
    resolved.extensions ||
    resolved.extension_label ||
    WIZARD_COPY_KEYS.some((key) => resolved[key])
  ) {
    // The wizard and its wording belong to picklist_multi alone; a type change
    // leaves all of it behind.
    resolved = {
      ...resolved,
      extensions: undefined,
      extension_label: undefined,
      ...clearedWizardCopy(),
    };
  }

  if (!resolved.id.trim()) return { resolved, error: 'Field ID is required' };
  if (!resolved.label.trim()) return { resolved, error: 'Field label is required' };

  if (resolved.type === 'table') {
    const columns = resolved.table_config?.columns ?? [];
    if (columns.length === 0) {
      return { resolved, error: 'Table fields must include at least one column' };
    }
    const columnIds = columns.map((column) => column.id.trim()).filter(Boolean);
    if (columnIds.length !== columns.length) {
      return { resolved, error: 'Every table column needs an ID' };
    }
    if (new Set(columnIds).size !== columnIds.length) {
      return { resolved, error: 'Table column IDs must be unique' };
    }
    if ((resolved.table_config?.row_mode ?? 'dynamic') === 'fixed') {
      const rows = resolved.table_config?.rows ?? [];
      const rowIds = rows.map((row) => row.id.trim()).filter(Boolean);
      if (rowIds.length !== rows.length) {
        return { resolved, error: 'Every fixed table row needs an ID' };
      }
      if (new Set(rowIds).size !== rowIds.length) {
        return { resolved, error: 'Fixed table row IDs must be unique' };
      }
    }
  }

  if (
    (resolved.type === 'select' || resolved.type === 'multi_select') &&
    !resolved.picklist_id
  ) {
    return { resolved, error: 'Please select a picklist for this field' };
  }
  if (
    resolved.type === 'picklist_multi' &&
    (!resolved.picklist_id || !resolved.picklist_id_2)
  ) {
    return { resolved, error: 'Please select both picklists for this field' };
  }
  const disallowed = disallowedExtensionType(resolved.extensions);
  if (disallowed) {
    return { resolved, error: `Extended fields cannot be of type ${disallowed}` };
  }
  // Without a document type there is nothing to upload against: it carries the
  // storage provider and the accepted extensions.
  if (resolved.type === 'document' && !resolved.document_config?.type_id) {
    return { resolved, error: 'Please select a document type for this field' };
  }

  return { resolved, error: null };
}
