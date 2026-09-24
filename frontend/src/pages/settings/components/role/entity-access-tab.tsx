"use client"

import type { ColumnDef } from "@tanstack/react-table"

import { type Role } from "@/lib/roles-data"
import { ENTITY_ACTIONS } from "@/lib/entity-data"
import type { EntityType } from "@/core/types"
import { useEntityTypes } from "@/core/hooks/useEntityTypes"
import { DataTable } from "@/core/components/DataTable"
import { ColorToggle } from "./shared/color-toggle"
import { ColumnHeaderLabel } from "./shared/column-header"

interface EntityAccessTabProps {
  role: Role
  entityPerms: Set<string>
  setEntityPerms: (value: Set<string> | ((prev: Set<string>) => Set<string>)) => void
  disabled?: boolean
}

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

export function EntityAccessTab({
  role,
  entityPerms,
  setEntityPerms,
  disabled = false,
}: EntityAccessTabProps) {
  const color = role.color
  const { entityTypes, loading, error } = useEntityTypes()

  const has = (type: string, action: string) => entityPerms.has(`${type}:${action}`)

  const toggle = (type: string, action: string) => {
    setEntityPerms((prev) => {
      const next = new Set(prev)
      const key = `${type}:${action}`
      if (next.has(key)) {
        // turning off view removes everything for that entity
        if (action === "view") {
          ENTITY_ACTIONS.forEach((a) => next.delete(`${type}:${a}`))
        } else {
          next.delete(key)
        }
      } else {
        next.add(key)
        // any access implies view
        if (action !== "view") {
          next.add(`${type}:view`)
        }
      }
      return next
    })
  }

  const columns: ColumnDef<EntityType, unknown>[] = [
    {
      id: "entity",
      header: "Entity",
      accessorFn: (e) => e.display_name || e.name,
      cell: ({ row }) => (
        <div className="min-w-0">
          <div className="text-sm font-semibold">{row.original.display_name || row.original.name}</div>
          {row.original.description && (
            <div className="text-xs text-muted-foreground">{row.original.description}</div>
          )}
        </div>
      ),
    },
    ...ENTITY_ACTIONS.map((a): ColumnDef<EntityType, unknown> => ({
      id: a,
      header: () => <ColumnHeaderLabel>{capitalize(a)}</ColumnHeaderLabel>,
      cell: ({ row }) => {
        const typeKey = row.original.name
        const isView = a === "view"
        const toggleDisabled = !isView && !has(typeKey, "view")
        return (
          <div className="flex justify-center">
            <ColorToggle
              checked={has(typeKey, a)}
              onCheckedChange={() => toggle(typeKey, a)}
              color={color}
              disabled={disabled || toggleDisabled}
            />
          </div>
        )
      },
      meta: { width: "78px" },
    })),
  ]

  return (
    <div>
      <p className="text-[13.5px] text-muted-foreground -mt-1 mb-[18px] max-w-[640px] leading-[1.55]">
        Choose which entity types this role can act on.{" "}
        <strong className="text-foreground font-semibold">View</strong> is required for any other
        action — turning it off clears the rest. Field-level rules live in the{" "}
        <strong className="text-foreground font-semibold">Forms</strong> tab.
      </p>
      {role.is_system && (
        <div className="mb-4 rounded-lg border border-info/30 bg-info-subtle px-3 py-2 text-sm text-info">
          System roles receive View, Create, Edit, and Delete access automatically.
        </div>
      )}

      {error ? (
        <div className="py-[28px] px-[18px] text-sm text-destructive">{error}</div>
      ) : (
        <DataTable
          label="Entity access"
          data={entityTypes}
          columns={columns}
          getRowId={(e) => e.id}
          isLoading={loading}
          enableSorting={false}
          className={disabled ? "opacity-40 pointer-events-none" : ""}
          emptyState={{ title: "No entity types found." }}
        />
      )}
    </div>
  )
}
