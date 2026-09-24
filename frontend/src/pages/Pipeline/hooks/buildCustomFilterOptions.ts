import type { FormSchema } from '@/core/types';
import type { FilterBarItem } from '@/skins';
import { getFormFields } from '@/shared/utils/entityForm';

/**
 * Turns each select/boolean schema field the viewer can see into an
 * available "Filters" bubble option — shared by the main /pipeline page
 * and the agent-mode PipelineBoardWidget so the two don't drift as field
 * types are added.
 */
export function buildCustomFilterOptions(
  entitySchemas: FormSchema[],
  entityType: string,
  canViewField: (entityType: string, fieldId: string) => boolean,
): FilterBarItem[] {
  const seen = new Set<string>();
  const result: FilterBarItem[] = [];
  for (const schema of entitySchemas) {
    for (const field of getFormFields(schema)) {
      if (seen.has(field.id) || !canViewField(entityType, field.id)) continue;
      // multi_select/picklist_multi ("labels") fields store their value as
      // a JSON array, not a scalar like `select` — they still get the same
      // enum_values catalog, just rendered as a multi-value chip filter
      // (multiple picks OR together) instead of a single-choice dropdown.
      const isMultiValue = field.type === 'multi_select' || field.type === 'picklist_multi';
      const values = (field.type === 'select' || isMultiValue) && field.enum_values?.length
        ? field.enum_values
        : field.type === 'boolean'
          ? ['true', 'false']
          : null;
      if (!values) continue;
      seen.add(field.id);
      result.push({
        key: field.id,
        label: field.label,
        type: isMultiValue ? 'multiselect' : 'select',
        staticOptions: values,
        staticOptionLabels: field.enum_labels?.length
          ? field.enum_labels
          : field.type === 'boolean'
            ? ['Yes', 'No']
            : undefined,
      });
    }
  }
  return result.sort((a, b) => a.label.localeCompare(b.label));
}
