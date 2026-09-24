import { useCallback } from "react"

import {
  VISIBILITY_MODES,
  type FieldPermission,
  type VisibilityMode,
} from "@/lib/entity-data"

const DEFAULT_FP: FieldPermission = { view: false, edit: false, mask: false }

const keyOf = (entity: string, field: string) => `${entity}:${field}`

type SetFieldPerms = (
  value:
    | Record<string, FieldPermission>
    | ((prev: Record<string, FieldPermission>) => Record<string, FieldPermission>)
) => void

/**
 * Encapsulates all field-permission read/write logic for the Forms tab.
 * Components depend on these handlers, not on the permission key shape.
 */
export function useFieldPermissions(
  fieldPerms: Record<string, FieldPermission>,
  setFieldPerms: SetFieldPerms
) {
  const fpOf = useCallback(
    (entity: string, field: string): FieldPermission =>
      fieldPerms[keyOf(entity, field)] || DEFAULT_FP,
    [fieldPerms]
  )

  const setFP = useCallback(
    (entity: string, field: string, patch: Partial<FieldPermission>) => {
      setFieldPerms((prev) => ({
        ...prev,
        [keyOf(entity, field)]: { ...(prev[keyOf(entity, field)] || DEFAULT_FP), ...patch },
      }))
    },
    [setFieldPerms]
  )

  const setVis = useCallback(
    (entity: string, field: string, mode: VisibilityMode) => {
      const v = VISIBILITY_MODES[mode]
      setFieldPerms((prev) => {
        const cur = prev[keyOf(entity, field)] || DEFAULT_FP
        return {
          ...prev,
          [keyOf(entity, field)]: { view: v.view, mask: v.mask, edit: (v.view && !v.mask) ? cur.edit : false },
        }
      })
    },
    [setFieldPerms]
  )

  const setFormVis = useCallback(
    (entity: string, fields: Array<{ id: string }>, mode: VisibilityMode) => {
      const v = VISIBILITY_MODES[mode]
      setFieldPerms((prev) => {
        const next = { ...prev }
        fields.forEach((f) => {
          const cur = next[keyOf(entity, f.id)] || DEFAULT_FP
          next[keyOf(entity, f.id)] = { view: v.view, mask: v.mask, edit: (v.view && !v.mask) ? cur.edit : false }
        })
        return next
      })
    },
    [setFieldPerms]
  )

  return { fpOf, setFP, setVis, setFormVis }
}
