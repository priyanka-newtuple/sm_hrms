"use client"

import { useMemo, useState } from "react"

import { type Role } from "@/lib/roles-data"
import { type FieldPermission } from "@/lib/entity-data"
import { useEntityTypes } from "@/core/hooks/useEntityTypes"
import { useFormSchemas } from "@/core/hooks/useFormSchemas"
import { useWorkflowFieldsByEntityType } from "@/shared/hooks"
import { unionEntityFormSchemas } from "@/lib/state-machine/entitySchema"
import { SearchInput } from "./shared/search-input"
import { useFieldPermissions } from "./forms/useFieldPermissions"
import { EntityTabs } from "./forms/entity-tabs"
import { EntityViewWarning } from "./forms/entity-view-warning"
import { VisibilityLegend } from "./forms/visibility-legend"
import { FormCard } from "./forms/form-card"

interface FormsTabProps {
  role: Role
  fieldPerms: Record<string, FieldPermission>
  setFieldPerms: (
    value:
      | Record<string, FieldPermission>
      | ((prev: Record<string, FieldPermission>) => Record<string, FieldPermission>)
  ) => void
  entityPerms: Set<string>
  disabled?: boolean
}

export function FormsTab({
  role,
  fieldPerms,
  setFieldPerms,
  entityPerms,
  disabled = false,
}: FormsTabProps) {
  const color = role.color
  const [selectedEntity, setSelectedEntity] = useState("")
  const [query, setQuery] = useState("")

  const { entityTypes, loading: entitiesLoading, error: entitiesError } = useEntityTypes()
  const { schemas, loading: formsLoading, error: formsError } = useFormSchemas()
  const workflowFieldsByEntityType = useWorkflowFieldsByEntityType()
  const { fpOf, setFP, setVis, setFormVis } = useFieldPermissions(fieldPerms, setFieldPerms)

  // Fall back to the first entity until the user picks one — no effect needed.
  const activeEntity = selectedEntity || (entityTypes.length ? entityTypes[0].name : "")

  // Every field surface of the active entity: its Forms plus, for a type whose
  // fields come from Method Blocks (workflow entity_schema, possibly with no
  // Form at all), a synthetic "Workflow fields" card. Grants are keyed by
  // (entity, field name) either way — the card is only grouping.
  const forms = useMemo(
    () =>
      unionEntityFormSchemas(activeEntity || undefined, {
        formSchemas: schemas,
        workflowFields: workflowFieldsByEntityType[activeEntity],
      }),
    [schemas, activeEntity, workflowFieldsByEntityType]
  )

  const entityViewable = entityPerms.has(`${activeEntity}:view`)
  const term = query.trim().toLowerCase()
  const loading = entitiesLoading || formsLoading
  const error = entitiesError || formsError

  if (loading) {
    return <div className="py-[28px] text-sm text-muted-foreground">Loading forms…</div>
  }
  if (error) {
    return <div className="py-[28px] text-sm text-destructive">{error}</div>
  }
  if (!entityTypes.length) {
    return <div className="py-[28px] text-sm text-muted-foreground">No entity types found.</div>
  }

  return (
    <div>
      <EntityTabs
        entityTypes={entityTypes}
        activeEntity={activeEntity}
        entityPerms={entityPerms}
        color={color}
        onSelect={setSelectedEntity}
      />

      {!entityViewable && <EntityViewWarning entity={activeEntity} />}

      <div className="flex items-center justify-between gap-[14px] flex-wrap mb-4">
        <SearchInput value={query} onChange={setQuery} placeholder="Search fields..." />
        <VisibilityLegend />
      </div>

      {forms.length === 0 && (
        <div className="border border-dashed border-border rounded-[14px] py-[28px] text-center text-sm text-muted-foreground">
          No fields available for {activeEntity} — add a Form, or pin a Method Block to its
          published workflow.
        </div>
      )}

      <div
        className="flex flex-col gap-4"
        style={{
          opacity: entityViewable ? 1 : 0.55,
          pointerEvents: entityViewable ? "auto" : "none",
        }}
      >
        {forms.map((f) => (
          <FormCard
            key={f.schema_key}
            form={f}
            term={term}
            color={color}
            disabled={disabled}
            fpOf={(field) => fpOf(activeEntity, field)}
            onSetFieldVisibility={(field, mode) => setVis(activeEntity, field, mode)}
            onToggleFieldEdit={(field) => setFP(activeEntity, field, { edit: !fpOf(activeEntity, field).edit })}
            onSetFormVisibility={(fields, mode) => setFormVis(activeEntity, fields, mode)}
          />
        ))}
      </div>
    </div>
  )
}
