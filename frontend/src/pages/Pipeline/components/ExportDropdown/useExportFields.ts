import { useMemo, useState } from 'react';
import type { PipelineListEntity, PipelineSchemaField } from '@/shared/types/pipeline';
import {
  deriveExportFields,
  defaultSelectedKeys,
  orderSelectedFields,
} from '@/lib/export/fields';

/** Owns field derivation + selection state for the export picker. */
export function useExportFields(
  entities: PipelineListEntity[],
  schemaFields: PipelineSchemaField[],
) {
  const fields = useMemo(
    () => deriveExportFields(entities, schemaFields),
    [entities, schemaFields],
  );

  // A stable signature of the available field keys. We re-seed the default
  // selection only when this *content* changes — never on mere array-identity
  // churn from parent re-renders, which would otherwise reset the user's
  // checkboxes on every render and make selection appear frozen.
  const fieldsSignature = useMemo(() => fields.map((f) => f.key).join('|'), [fields]);

  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(() =>
    defaultSelectedKeys(fields),
  );
  const [seededSignature, setSeededSignature] = useState(fieldsSignature);
  if (seededSignature !== fieldsSignature) {
    setSeededSignature(fieldsSignature);
    setSelectedKeys(defaultSelectedKeys(fields));
  }

  const systemFields = useMemo(() => fields.filter((f) => f.group === 'system'), [fields]);
  const dataFields = useMemo(() => fields.filter((f) => f.group === 'data'), [fields]);

  const toggle = (key: string) =>
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  /** Select or deselect a specific set of field keys (e.g. the currently
   *  visible/filtered fields in a group). */
  const setMany = (keys: string[], on: boolean) =>
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      for (const k of keys) {
        if (on) next.add(k);
        else next.delete(k);
      }
      return next;
    });

  const selectedFields = useMemo(
    () => orderSelectedFields(fields, selectedKeys),
    [fields, selectedKeys],
  );

  return {
    systemFields,
    dataFields,
    selectedKeys,
    isSelected: (key: string) => selectedKeys.has(key),
    toggle,
    setMany,
    selectedFields,
  };
}
