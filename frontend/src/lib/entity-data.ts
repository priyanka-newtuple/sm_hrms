import type { EntityCondition, EntityFilter } from "@/core/types/rbac"
export type { EntityCondition, EntityFilter } from "@/core/types/rbac"

// Role permission primitives — entity actions, field-level visibility modes,
// and default permission seeds. Entity/form data itself comes from the live API
// (useEntityTypes / useFormSchemas), not from here.

export const ENTITY_ACTIONS = ["view", "create", "edit", "delete"] as const
export type EntityAction = (typeof ENTITY_ACTIONS)[number]

// Strip namespace ("ATS.Candidate" -> "Candidate") so keys match permission seeds.
export const simpleName = (name: string) => (name.includes(".") ? name.split(".").pop()! : name)

export interface FieldPermission {
  view: boolean
  edit: boolean
  mask: boolean
}

export const MAX_ENTITY_READ_FILTER_CONDITIONS = 50

/**
 * Returns true if the operator expects comma-separated membership list values ("in" or "not_in").
 */
export function isMembershipOperator(operator: string): boolean {
  return operator === "in" || operator === "not_in"
}

/**
 * Validates that an EntityCondition has a selected field and a valid value matching
 * backend constraints:
 * - Max length of 256 characters.
 * - For membership operators ("in", "not_in"): at least one non-empty value in the comma-separated list.
 * - For scalar operators ("==", "!="): non-empty trimmed value with no commas.
 */
export function isEntityConditionComplete(condition: EntityCondition): boolean {
  if (!condition.entity_field.trim() || condition.condition_value.length > 256) return false
  return isMembershipOperator(condition.operator)
    ? condition.condition_value.split(",").some((value) => value.trim().length > 0)
    : condition.condition_value.trim().length > 0 && !condition.condition_value.includes(",")
}

/**
 * Validates that an EntityFilter has between 1 and MAX_ENTITY_READ_FILTER_CONDITIONS
 * conditions, and every condition is complete and valid.
 */
export function isEntityFilterComplete(filter: EntityFilter): boolean {
  return (
    filter.conditions.length > 0 &&
    filter.conditions.length <= MAX_ENTITY_READ_FILTER_CONDITIONS &&
    filter.conditions.every(isEntityConditionComplete)
  )
}

// Field value visibility modes (None, Visible, or Masked).
export const VISIBILITY_MODES = {
  none:   { view: false, mask: false, label: "None",    icon: "eye-off", tone: "#A1A1AA" },
  full:   { view: true,  mask: false, label: "Visible", icon: "eye",     tone: "#0D9488" },
  masked: { view: true,  mask: true,  label: "Masked",  icon: "mask",    tone: "#D97706" },
} as const

export type VisibilityMode = keyof typeof VISIBILITY_MODES

export function getVisibilityMode(fp: FieldPermission): VisibilityMode {
  if (!fp.view) return "none"
  return fp.mask ? "masked" : "full"
}
