/**
 * Field Filteration picker sources.
 *
 * Guards two properties:
 *  1. `resolveEntityFormSchemas` stays strictly additive — for a Forms-based
 *     entity type the output is identical whatever `scope` is passed and
 *     whether workflowFields are supplied, because the Forms-first branch
 *     returns before either is consulted. This is what keeps the Relations
 *     modal / Form Config pickers unchanged by the role-picker work.
 *  2. The picker hook unions Forms with Method-Block `entity_schema` fields:
 *     Forms-only and Method-Block-only types keep their exact lists, and a
 *     hybrid (mid-migration) type offers both, deduped with the Form
 *     definition winning a name collision.
 */
import { renderHook } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { resolveEntityFormSchemas, unionEntityFormSchemas } from "@/lib/state-machine/entitySchema"
import type { EntityType, FormField, FormSchema } from "@/core/types"
import type { EntityField } from "@/lib/state-machine/types"
import { useFilteredEntityTypes } from "./useFilteredEntityTypes"

const formField = (id: string): FormField => ({
  id,
  label: id,
  type: "text",
  required: false,
  system: false,
})

const form = (entityType: string, name: string, fieldIds: string[]): FormSchema => ({
  id: `${entityType}-${name}`,
  schema_key: `${entityType}__${name}`,
  name,
  entity_type: entityType,
  version: 1,
  is_active: true,
  display_order: 0,
  schema: { fields: fieldIds.map(formField) },
  created_at: "",
  updated_at: "",
})

const entityField = (field: string): EntityField => ({
  field,
  type: "string",
  required: false,
  nullable: true,
  default: "",
  enum_values: [],
  picklist_id: null,
  description: field,
})

const entity = (name: string): EntityType =>
  ({ entity_type_id: name, name, display_name: name, is_active: true }) as unknown as EntityType

// Mirrors real data: perkin_client's Form has exactly these two fields.
const PERKIN_CLIENT_FORM = form("perkin_client", "Client", ["identifier", "name"])
// Mirrors real data: request has no Form; its workflow entity_schema has this.
const REQUEST_WORKFLOW_FIELDS = [entityField("request_flow_name")]

const ids = (fields: FormField[]) => fields.map((f) => f.id)

describe("resolveEntityFormSchemas is scope-invariant for Forms-based types", () => {
  it("returns the same Forms whether scope is state or union, with or without workflowFields", () => {
    const base = { formSchemas: [PERKIN_CLIENT_FORM] }
    const asUnion = resolveEntityFormSchemas("perkin_client", { scope: "union", ...base })
    const asState = resolveEntityFormSchemas("perkin_client", { scope: "state", ...base })
    const withWorkflowFields = resolveEntityFormSchemas("perkin_client", {
      scope: "union",
      ...base,
      workflowFields: [entityField("sneaky_extra")],
    })
    expect(asUnion).toEqual([PERKIN_CLIENT_FORM])
    expect(asState).toEqual(asUnion)
    // Forms win outright: a workflow field never leaks into a Forms-based type here.
    expect(withWorkflowFields).toEqual(asUnion)
  })
})

describe("useFilteredEntityTypes unions Forms with Method-Block fields", () => {
  it("Forms-only type keeps its exact Form field list", () => {
    const { result } = renderHook(() =>
      useFilteredEntityTypes([entity("perkin_client")], [PERKIN_CLIENT_FORM], {}, "")
    )
    expect(ids(result.current[0].fields)).toEqual(["identifier", "name"])
  })

  it("Method-Block-only type keeps its exact entity_schema field list", () => {
    const { result } = renderHook(() =>
      useFilteredEntityTypes([entity("request")], [], { request: REQUEST_WORKFLOW_FIELDS }, "")
    )
    expect(ids(result.current[0].fields)).toEqual(["request_flow_name"])
  })

  it("hybrid type offers both sources, deduped with the Form winning a collision", () => {
    const hybridForm = form("hybrid_type", "Legacy", ["legacy_a", "shared_x"])
    const hybridWorkflowFields = [entityField("shared_x"), entityField("mb_b")]
    const { result } = renderHook(() =>
      useFilteredEntityTypes(
        [entity("hybrid_type")],
        [hybridForm],
        { hybrid_type: hybridWorkflowFields },
        ""
      )
    )
    const fields = result.current[0].fields
    expect(ids(fields)).toEqual(["legacy_a", "shared_x", "mb_b"])
    // The colliding name kept the Form's definition (a FormField from the form
    // fixture), not the entity_schema-derived one whose label is the field key.
    const sharedX = fields.find((f) => f.id === "shared_x")
    expect(sharedX?.label).toBe("shared_x")
    expect(sharedX?.type).toBe("text")
  })

  it("entity_schema identifier never duplicates into the list", () => {
    const { result } = renderHook(() =>
      useFilteredEntityTypes(
        [entity("request")],
        [],
        { request: [entityField("identifier"), entityField("request_flow_name")] },
        ""
      )
    )
    // buildFallbackFormSchemaFromEntitySchema drops `identifier` by design.
    expect(ids(result.current[0].fields)).toEqual(["request_flow_name"])
  })
})

describe("unionEntityFormSchemas (shared by Field Filteration and role field permissions)", () => {
  it("hybrid: appends only the Method-Block extras as a separate Workflow fields card", () => {
    const hybridForm = form("hybrid_type", "Legacy", ["legacy_a", "shared_x"])
    const out = unionEntityFormSchemas("hybrid_type", {
      formSchemas: [hybridForm],
      workflowFields: [entityField("shared_x"), entityField("mb_b")],
    })
    expect(out).toHaveLength(2)
    expect(out[0]).toEqual(hybridForm)
    expect(out[1].name).toBe("Workflow fields")
    expect(out[1].schema.fields.map((f) => f.id)).toEqual(["mb_b"])
  })

  it("Form-less: returns exactly the fallback card once, never twice", () => {
    const out = unionEntityFormSchemas("request", {
      formSchemas: [],
      workflowFields: REQUEST_WORKFLOW_FIELDS,
    })
    expect(out).toHaveLength(1)
    expect(out[0].name).toBe("Workflow fields")
    expect(out[0].schema.fields.map((f) => f.id)).toEqual(["request_flow_name"])
  })

  it("Forms-only: byte-identical to the Forms list, no synthetic card", () => {
    const out = unionEntityFormSchemas("perkin_client", { formSchemas: [PERKIN_CLIENT_FORM] })
    expect(out).toEqual([PERKIN_CLIENT_FORM])
  })
})
