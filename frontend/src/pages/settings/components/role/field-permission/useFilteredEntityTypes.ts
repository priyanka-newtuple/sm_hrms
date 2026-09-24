import { useMemo } from "react"

import { unionEntityFormSchemas } from "@/lib/state-machine/entitySchema"
import type { EntityType, FormField, FormSchema } from "@/core/types"
import type { EntityField } from "@/lib/state-machine/types"

export interface FilteredEntitySection {
  entity: EntityType
  fields: FormField[]
}

/** Entity types matching the search term, each paired with its merged, de-duplicated
 * field list from `unionEntityFormSchemas`: every active Form's fields UNIONED with
 * the Method-Block-composed fields on the type's published workflow `entity_schema`,
 * the Form definition winning a name collision. A hybrid type (old Form alongside
 * new Method-Block fields, the deliberate mid-migration state) stores values from
 * both sources in the same `entities.data` the saved condition is evaluated
 * against, so both are filterable. Matches the backend's
 * `RolesModelService.get_entity_type_schema_fields`, which merges the same two
 * sources. */
export function useFilteredEntityTypes(
  entityTypes: EntityType[],
  schemas: FormSchema[],
  workflowFieldsByEntityType: Record<string, EntityField[]>,
  term: string
): FilteredEntitySection[] {
  return useMemo(() => {
    return entityTypes
      .filter((entity) => !term || (entity.display_name || entity.name).toLowerCase().includes(term))
      .map((entity) => {
        const resolved = unionEntityFormSchemas(entity.name, {
          formSchemas: schemas,
          workflowFields: workflowFieldsByEntityType[entity.name],
        })
        const seen = new Set<string>()
        const fields: FormField[] = []
        resolved.forEach((form) => {
          form.schema.fields.forEach((field) => {
            if (!seen.has(field.id)) {
              seen.add(field.id)
              fields.push(field)
            }
          })
        })
        return { entity, fields }
      })
  }, [entityTypes, schemas, workflowFieldsByEntityType, term])
}
