import type { EntityPermission } from "@/core/types/rbac"
import { useState } from "react"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import type { EntityType, FormField } from "@/core/types"
import { isEntityFilterComplete, type EntityFilter } from "@/lib/entity-data"
import { EntityConditionRow } from "./entity-condition-row"
import { buildRolePayload, readEntityFilter } from "../detail/role-payload"

afterEach(cleanup)
const initial: EntityFilter = { conditions: [{ conjunction: "AND", entity_field: "name", operator: "==", value_source: "LITERAL", condition_value: "Alex" }] }
const entity = { id: "1", name: "Candidate", display_name: "Candidate" } as EntityType
const fields = [{ id: "name", label: "Name" }, { id: "status", label: "Status" }] as FormField[]

function Editor({ disabled = false }: { disabled?: boolean }) {
  const [filter, setFilter] = useState<EntityFilter | undefined>(initial)
  return <>
    <EntityConditionRow entity={entity} fields={fields} condition={filter} entityViewable disabled={disabled}
      onToggle={() => setFilter(filter ? undefined : initial)} onChange={setFilter} />
    <button disabled={filter !== undefined && !isEntityFilterComplete(filter)}>Save</button>
    <output data-testid="payload">{JSON.stringify(buildRolePayload({
      granted: new Set(), entityPerms: new Set(["Candidate:view", "Candidate:edit"]),
      entityConditions: filter ? { Candidate: filter } : {}, fieldPerms: {},
      transitionPerms: new Set(), workflowPerms: new Set(), isKnownEntityType: () => true,
    }).payload.entity_permissions)}</output>
  </>
}

describe("mixed role read conditions", () => {
  it("adds AND and OR rows, blocks incomplete saves, and serializes only view filters", () => {
    render(<Editor />)
    fireEvent.click(screen.getByText("+ AND condition"))
    expect((screen.getByText("Save") as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByLabelText("Field for condition 2"), { target: { value: "status" } })
    fireEvent.change(screen.getByLabelText("Value for condition 2"), { target: { value: "Active" } })
    fireEvent.click(screen.getByText("+ OR condition"))
    fireEvent.change(screen.getByLabelText("Field for condition 3"), { target: { value: "name" } })
    fireEvent.change(screen.getByLabelText("Value for condition 3"), { target: { value: "Sam" } })
    expect((screen.getByText("Save") as HTMLButtonElement).disabled).toBe(false)
    const payload = JSON.parse(screen.getByTestId("payload").textContent!)
    expect(payload[0].read_filter.conditions.map((c: { conjunction: string }) => c.conjunction)).toEqual(["AND", "AND", "OR"])
    expect(payload[1].read_filter).toBeUndefined()
    fireEvent.change(screen.getByLabelText("Connector before condition 2"), { target: { value: "OR" } })
    expect((screen.getByLabelText("Connector before condition 2") as HTMLSelectElement).value).toBe("OR")
    fireEvent.click(screen.getByLabelText("Remove condition 1"))
    expect((screen.getByLabelText("Value for condition 1") as HTMLInputElement).value).toBe("Active")
    fireEvent.click(screen.getByLabelText("Remove condition 2"))
    expect(screen.queryByText("Remove")).toBeNull()
  })

  it("loads legacy filters and preserves every mixed connector on reload", () => {
    const legacy: EntityPermission = { id: "1", entity_type: "Candidate", action: "view", allowed: true,
      entity_field: "name", operator: "==", condition_value: "Alex" }
    expect(readEntityFilter(legacy)).toEqual(initial)
    const compound = { conditions: [...initial.conditions, { ...initial.conditions[0], conjunction: "OR" as const, condition_value: "Sam" }] }
    expect(readEntityFilter({ ...legacy, read_filter: compound })).toEqual(compound)
    expect(readEntityFilter({ ...legacy, action: "edit" })).toBeUndefined()
  })

  it.each(["in", "not_in"])("validates and round-trips %s lists", (operator) => {
    render(<Editor />)
    fireEvent.change(screen.getByLabelText("Operator for condition 1"), { target: { value: operator } })
    expect((screen.getByLabelText("Value for condition 1") as HTMLInputElement).placeholder).toBe("store-A, store-B")
    fireEvent.change(screen.getByLabelText("Value for condition 1"), { target: { value: " , , " } })
    expect((screen.getByText("Save") as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByLabelText("Value for condition 1"), { target: { value: " Alex, Sam, , Alex " } })
    expect((screen.getByText("Save") as HTMLButtonElement).disabled).toBe(false)
    const [permission] = JSON.parse(screen.getByTestId("payload").textContent!)
    expect(readEntityFilter(permission)?.conditions[0]).toMatchObject({ operator, condition_value: " Alex, Sam, , Alex " })
    fireEvent.click(screen.getByRole("switch"))
    const [unfiltered] = JSON.parse(screen.getByTestId("payload").textContent!)
    expect(unfiltered.read_filter).toBeUndefined()
  })

  it("prevents editing read-only roles", () => {
    render(<Editor disabled />)
    expect((screen.getByText("+ AND condition") as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByLabelText("Value for condition 1") as HTMLInputElement).disabled).toBe(true)
  })

  it("rejects whitespace and empty condition lists", () => {
    expect(isEntityFilterComplete({ conditions: [] })).toBe(false)
    expect(isEntityFilterComplete({ conditions: [{ ...initial.conditions[0], condition_value: "  " }] })).toBe(false)
    expect(isEntityFilterComplete({ conditions: [{ ...initial.conditions[0], condition_value: "Alex,Sam" }] })).toBe(false)
  })

  it("blocks comma in scalar operators with an inline warning", () => {
    render(<Editor />)
    fireEvent.change(screen.getByLabelText("Value for condition 1"), { target: { value: "Alex,Sam" } })
    expect((screen.getByText("Save") as HTMLButtonElement).disabled).toBe(true)
    expect(
      screen.getByText(
        'Commas are not allowed with “Equals” or “Not equals”. Use “Is one of” or “Is not one of” to match multiple values.'
      )
    ).toBeDefined()
    fireEvent.change(screen.getByLabelText("Operator for condition 1"), { target: { value: "in" } })
    expect((screen.getByText("Save") as HTMLButtonElement).disabled).toBe(false)
    expect(
      screen.queryByText(
        'Commas are not allowed with “Equals” or “Not equals”. Use “Is one of” or “Is not one of” to match multiple values.'
      )
    ).toBeNull()
  })
})
