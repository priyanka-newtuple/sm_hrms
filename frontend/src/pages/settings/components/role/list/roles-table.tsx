import { useMemo, useState } from "react"
import type { ColumnDef } from "@tanstack/react-table"

import { DataTable, DataTableToolbar } from "@/core/components/DataTable"
import { hexToRgba } from "@/lib/roles-data"
import type { RoleListItem as Role } from "@/core/types"
import { SearchInput } from "../shared/search-input"
import { TypeBadge } from "../shared/type-badge"
import { PriorityBar } from "../shared/priority-bar"
import { UsersIcon } from "../shared/icons"

const DEFAULT_COLOR = "#71717A"

interface RolesTableProps {
  roles: Role[]
  onSelectRole?: (roleId: string) => void
}

export function RolesTable({ roles, onSelectRole }: RolesTableProps) {
  const [query, setQuery] = useState("")

  // Only the text filter lives here — column sorting is the table's own.
  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return roles
    return roles.filter((role) =>
      `${role.display_name} ${role.name} ${role.description || ""}`
        .toLowerCase()
        .includes(needle),
    )
  }, [roles, query])

  const columns: ColumnDef<Role, unknown>[] = [
    {
      id: "display_name",
      header: "Role",
      accessorFn: (role) => role.display_name,
      cell: ({ row }) => {
        const color = row.original.color ?? DEFAULT_COLOR
        return (
          <div className="flex min-w-0 items-center gap-3">
            <span
              className="size-2.5 shrink-0 rounded-[3px]"
              style={{
                backgroundColor: color,
                boxShadow: `0 0 0 3px ${hexToRgba(color, 0.14)}`,
              }}
            />
            <span className="truncate text-sm font-medium text-foreground">
              {row.original.display_name}
            </span>
          </div>
        )
      },
      meta: { width: "16rem" },
    },
    {
      id: "description",
      header: "Description",
      accessorFn: (role) => role.description ?? "",
      cell: ({ row }) =>
        row.original.description ? (
          // Capped so a long description truncates instead of stretching the grid.
          <span
            className="block max-w-[26rem] truncate text-[12.5px] text-muted-foreground"
            title={row.original.description}
          >
            {row.original.description}
          </span>
        ) : (
          <span className="text-[12.5px] text-muted-foreground/50">—</span>
        ),
    },
    {
      id: "is_system",
      header: "Type",
      accessorFn: (role) => (role.is_system ? 1 : 0),
      cell: ({ row }) => (
        <TypeBadge
          isSystem={row.original.is_system}
          color={row.original.color ?? DEFAULT_COLOR}
        />
      ),
      meta: { width: "8rem" },
    },
    {
      id: "priority",
      header: "Priority",
      accessorFn: (role) => role.priority,
      cell: ({ row }) => (
        <PriorityBar
          priority={row.original.priority}
          color={row.original.color ?? DEFAULT_COLOR}
        />
      ),
      meta: { width: "12rem" },
    },
    {
      id: "user_count",
      header: "Members",
      accessorFn: (role) => role.user_count,
      cell: ({ row }) => (
        <span
          className={`inline-flex items-center gap-1.5 text-[13.5px] tabular-nums ${
            row.original.user_count ? "text-foreground" : "text-muted-foreground/60"
          }`}
        >
          <span className="inline-flex text-muted-foreground/60">
            <UsersIcon width={14} height={14} />
          </span>
          {row.original.user_count}
        </span>
      ),
      meta: { width: "8rem" },
    },
  ]

  return (
    <DataTable
      label="Roles"
      data={rows}
      columns={columns}
      getRowId={(role) => role.id}
      onRowClick={onSelectRole ? (role) => onSelectRole(role.id) : undefined}
      initialSorting={[{ id: "priority", desc: true }]}
      toolbar={
          <DataTableToolbar
          left={
            <SearchInput value={query} onChange={setQuery} placeholder="Search roles…" />
          }
          right={
            <span className="text-[12.5px] text-muted-foreground">
              {rows.length} of {roles.length}
            </span>
          }
          />
        }
      emptyState={{
        title: query ? `No roles match “${query}”.` : "No roles yet",
      }}
    />
  )
}
