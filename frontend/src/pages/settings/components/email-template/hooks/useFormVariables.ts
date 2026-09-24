import { useEffect, useMemo, useState } from "react";
import { formSchemas as formSchemasApi } from "../../../../../core/services/api";
import type { FormSchema } from "../../../../../core/types";
import type { FormOption, Variable } from "../types";

interface FormVariables {
  formOptions: FormOption[];
  availableVariables: Variable[];
}

export function useFormVariables(
  entityType: string | null,
  formId: string | null,
): FormVariables {
  const [schemas, setSchemas] = useState<FormSchema[]>([]);
  const [loadedForEntity, setLoadedForEntity] = useState<string | null>(null);

  useEffect(() => {
    const trimmed = entityType?.trim();

    if (!trimmed) {
      setSchemas([]);
      setLoadedForEntity(null);
      return;
    }

    let cancelled = false;

    formSchemasApi
      .list(trimmed)
      .then((res) => {
        if (cancelled) return;
        setSchemas(res.items);
        setLoadedForEntity(trimmed);
      })
      .catch(() => {
        if (!cancelled) {
          setSchemas([]);
          setLoadedForEntity(trimmed);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [entityType]);

  const formOptions = useMemo<FormOption[]>(
    () =>
      schemas.map((s) => ({
        value: s.id,
        label: s.name,
        fieldCount: s.schema.fields.length,
        isActive: s.is_active,
      })),
    [schemas],
  );

  const availableVariables = useMemo<Variable[]>(() => {
    const trimmedEntity = entityType?.trim() ?? null;
    const trimmedFormId = formId?.trim() ?? null;

    if (!trimmedEntity || !trimmedFormId || loadedForEntity !== trimmedEntity) return [];

    const schema = schemas.find((s) => s.id === trimmedFormId);
    if (!schema) return [];

    return schema.schema.fields.map((f) => ({
      key: f.id,
      label: f.label || f.id,
      desc: f.type,
    }));
  }, [entityType, formId, schemas, loadedForEntity]);

  return { formOptions, availableVariables };
}
