import { useEffect, useState } from 'react';
import { formSchemas } from '@/core/services/api';
import type { FormSchema } from '@/core/types';

function normalizeType(entityType: string): string {
  return entityType.replace(/^ATS\./i, '').trim().toLowerCase();
}

export function useEntitySchemaFor(entityType: string | undefined): FormSchema | null {
  const [schema, setSchema] = useState<FormSchema | null>(null);

  useEffect(() => {
    if (!entityType) {
      setSchema(null);
      return;
    }
    let cancelled = false;
    const target = normalizeType(entityType);
    formSchemas
      .list()
      .then((resp) => {
        if (cancelled) return;
        const match = resp.items.find(
          (s) => s.is_active && normalizeType(s.entity_type) === target,
        );
        setSchema(match ?? null);
      })
      .catch(() => {
        if (!cancelled) setSchema(null);
      });
    return () => {
      cancelled = true;
    };
  }, [entityType]);

  return schema;
}
