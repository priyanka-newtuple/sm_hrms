import { useEffect, useState } from "react";
import { entityTypes as entityTypesApi } from "../../../../../core/services/api";
import type { EntityType } from "../types";

const FALLBACK: EntityType[] = [{ value: null, label: "— none —" }];

export function useEntityTypes(): EntityType[] {
  const [entityTypes, setEntityTypes] = useState<EntityType[]>(FALLBACK);

  useEffect(() => {
    let cancelled = false;

    entityTypesApi
      .list()
      .then((response) => {
        if (cancelled) return;
        setEntityTypes([
          { value: null, label: "— none —" },
          ...response.items.map((et) => ({
            value: et.name,
            label: et.display_name?.trim() || et.name,
          })),
        ]);
      })
      .catch(() => {
        if (!cancelled) setEntityTypes(FALLBACK);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return entityTypes;
}
