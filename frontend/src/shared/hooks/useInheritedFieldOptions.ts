import { useEffect, useState } from 'react';

import { entityTypes as entityTypesApi } from '@/core/services/api';

/** Upper bound for fetching entity types to build the id ↔ name map (org type count is small). */
const ENTITY_TYPE_FETCH_LIMIT = 500;

/** One inherited field available on an entity type (a relation-declaration target). */
export interface InheritedFieldOption {
  /** Local field name — the key the value resolves under, used as `$entity.<id>`. */
  id: string;
  /** Human name of the entity type the value is inherited from, for display. */
  sourceEntity?: string;
  /** 'SNAPSHOT' (frozen at link time) or 'REFERENCE' (live). */
  relationType: string;
}

/**
 * Inherited fields for an entity type — fields pulled from a related entity via a
 * relation declaration (including the auto `<parent>_id`). The backend merges these
 * into the entity's `data` at read time, so a connector bound to this type can
 * reference them as `$entity.<field>`. Surfaced here so the connector picker can
 * offer them as clearly-labeled, read-only chips.
 */
export function useInheritedFieldOptions(entityType: string | undefined): InheritedFieldOption[] {
  const [fields, setFields] = useState<InheritedFieldOption[]>([]);

  useEffect(() => {
    if (!entityType || entityType === 'entity') {
      setFields([]);
      return;
    }
    let cancelled = false;

    (async () => {
      try {
        // Relations reference types by id; resolve the bound type's name → id and
        // keep an id → name map to label each inherited field's source type.
        const typeList = await entityTypesApi.list({ limit: ENTITY_TYPE_FETCH_LIMIT });
        const idToName = new Map<string, string>();
        let entityTypeId: string | undefined;
        for (const type of typeList.items) {
          const id = type.entity_type_id ?? type.id;
          idToName.set(id, type.display_name || type.name);
          if (type.name === entityType) entityTypeId = id;
        }
        if (!entityTypeId) {
          if (!cancelled) setFields([]);
          return;
        }

        const resp = await entityTypesApi.relations(entityTypeId);
        if (cancelled) return;
        setFields(
          resp.inherited_fields.map((item) => ({
            id: item.field,
            sourceEntity: idToName.get(item.source_entity_type_id),
            relationType: item.relation_type,
          })),
        );
      } catch (err) {
        if (!cancelled) {
          console.warn('Failed to load inherited field options', err);
          setFields([]);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [entityType]);

  return fields;
}

/** Inherited fields of one entity type, for grouped display. */
export interface InheritedFieldGroup {
  type: string;
  options: InheritedFieldOption[];
}

/** Inherited fields across multiple entity types, grouped per type (empty groups omitted). */
export function useInheritedFieldOptionsForTypes(typeNames: string[]): InheritedFieldGroup[] {
  const key = [...new Set(typeNames.filter((t) => t && t !== 'entity'))].join('|');
  const [groups, setGroups] = useState<InheritedFieldGroup[]>([]);

  useEffect(() => {
    const types = key ? key.split('|') : [];
    if (!types.length) {
      setGroups([]);
      return;
    }
    let cancelled = false;

    (async () => {
      try {
        const typeList = await entityTypesApi.list({ limit: ENTITY_TYPE_FETCH_LIMIT });
        const idToName = new Map<string, string>();
        const nameToId = new Map<string, string>();
        for (const type of typeList.items) {
          const id = type.entity_type_id ?? type.id;
          idToName.set(id, type.display_name || type.name);
          nameToId.set(type.name, id);
        }

        const results = await Promise.all(
          types.map(async (type) => {
            const entityTypeId = nameToId.get(type);
            if (!entityTypeId) return { type, options: [] };
            try {
              const resp = await entityTypesApi.relations(entityTypeId);
              return {
                type,
                options: resp.inherited_fields.map((item) => ({
                  id: item.field,
                  sourceEntity: idToName.get(item.source_entity_type_id),
                  relationType: item.relation_type,
                })),
              };
            } catch (err) {
              console.warn(`Failed to load inherited field options for ${type}`, err);
              return { type, options: [] };
            }
          }),
        );
        if (!cancelled) setGroups(results.filter((group) => group.options.length > 0));
      } catch (err) {
        if (!cancelled) {
          console.warn('Failed to load inherited field options', err);
          setGroups([]);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [key]);

  return groups;
}
