"use client"

import { useState } from "react"

import { type Role } from "@/lib/roles-data"
import { type EntityFilter } from "@/lib/entity-data"
import { useEntityTypes } from "@/core/hooks/useEntityTypes"
import { useFormSchemas } from "@/core/hooks/useFormSchemas"
import { useWorkflowFieldsByEntityType } from "@/shared/hooks"
import { SearchInput } from "./shared/search-input"
import { useFilteredEntityTypes } from "./field-permission/useFilteredEntityTypes"
import { EntityConditionRow } from "./field-permission/entity-condition-row"

interface FieldPermissionTabProps {
  role: Role
  entityConditions: Record<string, EntityFilter>
  setEntityConditions: (
    value:
      | Record<string, EntityFilter>
      | ((prev: Record<string, EntityFilter>) => Record<string, EntityFilter>)
  ) => void
  entityPerms: Set<string>
  disabled?: boolean
}

const DEFAULT_FILTER: EntityFilter = {
  conditions: [{
    conjunction: "AND",
    entity_field: "",
    operator: "==",
    value_source: "LITERAL",
    condition_value: "",
  }],
}

/**
 * Entity field permission filter — narrows a role's `view` access on an
 * entity type to only records matching a field condition (e.g. Store ID
 * equals a specific store), per entity type. All entity types the org has
 * are listed, each with its own fields; turning the toggle off reverts that
 * entity type to full, unconditional read access — writes are never
 * affected by this feature, regardless of the condition.
 *
 * Fields come from the entity type's *forms* (each contributing its own
 * fields, including cross-entity reference fields) and, for a type with no
 * Form at all, from its published workflow's `entity_schema` — the fields
 * composed by pinned Method Blocks. Both end up as plain keys in
 * `entities.data`, which is what the saved condition is evaluated against,
 * so both are equally filterable. Matches the backend's
 * `RolesModelService.get_entity_type_schema_fields`.
 */
export function FieldPermissionTab({
  role,
  entityConditions,
  setEntityConditions,
  entityPerms,
  disabled = false,
}: FieldPermissionTabProps) {
  const color = role.color
  const [query, setQuery] = useState("")
  const { entityTypes, loading: entitiesLoading, error: entitiesError } = useEntityTypes()
  const { schemas, loading: formsLoading, error: formsError } = useFormSchemas()
  const workflowFieldsByEntityType = useWorkflowFieldsByEntityType()

  const term = query.trim().toLowerCase()
  const loading = entitiesLoading || formsLoading
  const error = entitiesError || formsError
  const sections = useFilteredEntityTypes(entityTypes, schemas, workflowFieldsByEntityType, term)

  const setCondition = (entityType: string, filter: EntityFilter) => {
    setEntityConditions((prev) => ({
      ...prev,
      [entityType]: filter,
    }))
  }

  const clearCondition = (entityType: string) => {
    setEntityConditions((prev) => {
      const next = { ...prev }
      delete next[entityType]
      return next
    })
  }

  if (loading) {
    return <div className="py-[28px] text-sm text-muted-foreground">Loading entity types…</div>
  }
  if (error) {
    return <div className="py-[28px] text-sm text-destructive">{error}</div>
  }
  if (!entityTypes.length) {
    return <div className="py-[28px] text-sm text-muted-foreground">No entity types found.</div>
  }

  return (
    <div>
      <p className="text-[13.5px] text-muted-foreground -mt-1 mb-[18px] max-w-[640px] leading-[1.55]">
        Narrow what this role can <strong className="text-foreground font-semibold">view</strong>{" "}
        for an entity type to only records matching your conditions (e.g. Store ID equals a specific
        store AND Status equals Active). Off means full read access, unchanged from today.{" "}
        <strong className="text-foreground font-semibold">Writes are never affected</strong> — a
        role that can edit/create/delete a record keeps that ability regardless of this filter.
      </p>

      <div className="mb-4">
        <SearchInput value={query} onChange={setQuery} placeholder="Search entity types..." />
      </div>

      {sections.length === 0 && (
        <div className="border border-dashed border-border rounded-[14px] py-[28px] text-center text-sm text-muted-foreground">
          No entity types match &quot;{query}&quot;.
        </div>
      )}

      <div className="flex flex-col gap-4">
        {sections.map(({ entity, fields }) => (
          <EntityConditionRow
            key={entity.id}
            entity={entity}
            fields={fields}
            condition={entityConditions[entity.name]}
            entityViewable={entityPerms.has(`${entity.name}:view`)}
            disabled={disabled}
            color={color}
            onToggle={() =>
              entityConditions[entity.name] ? clearCondition(entity.name) : setCondition(entity.name, { conditions: DEFAULT_FILTER.conditions.map((c) => ({ ...c })) })
            }
            onChange={(filter) => setCondition(entity.name, filter)}
          />
        ))}
      </div>
    </div>
  )
}
