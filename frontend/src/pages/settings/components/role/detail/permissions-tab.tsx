import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import type { ColumnDef } from "@tanstack/react-table"

import { type Role, hexToRgba } from "@/lib/roles-data"
import {
  ACTION_RANK,
  buildPermissionsConfig,
  type Action,
  type PermissionDefinition,
} from "@/lib/permissions-data"
import { permissions as permissionsApi } from "@/core/services/api"
import { DataTable, DataTableToolbar } from "@/core/components/DataTable"
import { useSkin } from "@/skins/SkinContext"
import { isOptionalPermissionResourceVisible } from "@/pages/settings/lib/constant"
import { SearchInput } from "../shared/search-input"
import { ColorToggle } from "../shared/color-toggle"
import { ColumnHeaderLabel } from "../shared/column-header"
import { ShieldIcon } from "../shared/icons"

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

interface PermissionsTabProps {
  role: Role
  granted: Set<string>
  setGranted: (value: Set<string> | ((prev: Set<string>) => Set<string>)) => void
  disabled?: boolean
}

export function PermissionsTab({
  role,
  granted,
  setGranted,
  disabled = false,
}: PermissionsTabProps) {
  const [query, setQuery] = useState("")
  const color = role.color
  const { skin } = useSkin()

  const { data: livePermissions, isLoading: permsLoading } = useQuery({
    queryKey: ['permissions', 'list'],
    queryFn: permissionsApi.list,
    staleTime: 5 * 60 * 1000,
  })

  const config = useMemo(() => {
    if (!livePermissions?.length) return null
    const defs: PermissionDefinition[] = livePermissions.map((p) => ({
      key: p.key,
      resource: p.resource,
      action: p.action,
      description: p.description ?? '',
    }))
    return buildPermissionsConfig(defs)
  }, [livePermissions])

  const resources = config?.RESOURCES ?? []
  const resMeta = config?.RESOURCE_META ?? {}
  const resActions = config?.RESOURCE_ACTIONS ?? {}
  const allKeys = config?.ALL_PERMISSION_KEYS ?? []
  const allActions = config?.ALL_ACTIONS ?? []
  const presets = config?.PERMISSION_PRESETS
  const effectiveGranted = useMemo(
    () => (role.is_system ? new Set(allKeys) : granted),
    [allKeys, granted, role.is_system]
  )

  const filteredResources = useMemo(() => {
    const term = query.trim().toLowerCase()
    return resources.filter(
      (r) =>
        isOptionalPermissionResourceVisible(r, skin.optionalSettingsTabs) &&
        (!term ||
          resMeta[r].label.toLowerCase().includes(term) ||
          r.includes(term) ||
          resMeta[r].blurb.toLowerCase().includes(term))
    )
  }, [query, resources, resMeta, skin.optionalSettingsTabs])

  if (permsLoading) return <div className="py-8 text-sm text-muted-foreground">Loading permissions…</div>
  if (!config) return <div className="py-8 text-sm text-muted-foreground">No permissions configured.</div>

  // Cascade-aware toggle
  const toggle = (resource: string, action: Action, forceOn?: boolean) => {
    setGranted((prev) => {
      const next = new Set(prev)
      const key = `${resource}:${action}`
      const acts = resActions[resource]
      const turnOn = forceOn != null ? forceOn : !next.has(key)
      const rank = ACTION_RANK[action]
      if (turnOn) {
        acts.forEach((a) => {
          if (ACTION_RANK[a] <= rank) next.add(`${resource}:${a}`)
        })
      } else {
        acts.forEach((a) => {
          if (ACTION_RANK[a] >= rank) next.delete(`${resource}:${a}`)
        })
      }
      return next
    })
  }

  const grantedCount = effectiveGranted.size

  const columns: ColumnDef<string, unknown>[] = [
    {
      id: "resource",
      header: "Resource",
      accessorFn: (r) => resMeta[r].label,
      cell: ({ row }) => {
        const r = row.original
        return (
          <div className="min-w-0">
            <div className="text-sm font-semibold">{resMeta[r].label}</div>
            <div className="text-xs text-muted-foreground">
              {resMeta[r].blurb} ·{" "}
              <span className="font-mono text-[11.5px] text-muted-foreground">{r}</span>
            </div>
          </div>
        )
      },
    },
    ...allActions.map((a): ColumnDef<string, unknown> => ({
      id: a,
      header: () => <ColumnHeaderLabel>{capitalize(a)}</ColumnHeaderLabel>,
      cell: ({ row }) => {
        const r = row.original
        const exists = resActions[r].includes(a)
        const key = `${r}:${a}`
        return (
          <div className="flex justify-center">
            {exists ? (
              <ColorToggle
                checked={effectiveGranted.has(key)}
                onCheckedChange={() => toggle(r, a)}
                color={color}
                disabled={disabled}
              />
            ) : (
              <span className="text-muted-foreground/50 text-lg leading-none">–</span>
            )}
          </div>
        )
      },
      meta: { width: "72px" },
    })),
  ]

  return (
    <div>
      {/* Granted summary bar */}
      <div
        className="flex items-center gap-3 p-[12px_16px] border border-border rounded-xl mb-[18px]"
        style={{ backgroundColor: hexToRgba(color, 0.05) }}
      >
        <span
          className="flex w-[30px] h-[30px] rounded-lg items-center justify-center flex-shrink-0"
          style={{
            backgroundColor: hexToRgba(color, 0.14),
            color: color,
          }}
        >
          <ShieldIcon width={17} height={17} />
        </span>
        <div className="flex-1">
          <div className="text-[13.5px] font-semibold">
            <span style={{ color: color }}>{grantedCount}</span> of {allKeys.length}{" "}
            permissions granted
          </div>
          <div
            className="h-[5px] rounded-[3px] mt-[6px] overflow-hidden max-w-[340px]"
            style={{ backgroundColor: hexToRgba(color, 0.14) }}
          >
            <div
              className="h-full rounded-[3px] transition-[width] duration-200"
              style={{
                width: `${(grantedCount / allKeys.length) * 100}%`,
                backgroundColor: color,
              }}
            />
          </div>
        </div>
      </div>

      <DataTable
        label="Permissions"
        data={filteredResources}
        columns={columns}
        getRowId={(r) => r}
        enableSorting={false}
        className={disabled ? "opacity-40 pointer-events-none" : ""}
        toolbar={
          <DataTableToolbar
            className="flex-wrap gap-y-2"
            left={
              <SearchInput value={query} onChange={setQuery} placeholder="Search resources…" />
            }
            right={
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[12.5px] text-muted-foreground mr-1">Apply template:</span>
                {[
                  ["No access", "none"],
                  ["Read-only", "read"],
                  ["Editor", "editor"],
                  ["Full access", "full"],
                ].map(([lbl, k]) => (
                  <button
                    key={k}
                    onClick={() => presets && setGranted(presets[k as keyof typeof presets]())}
                    disabled={disabled}
                    className="text-[12.5px] font-semibold py-[6px] px-[11px] rounded-[7px] border border-border bg-card text-foreground cursor-pointer transition-all hover:border-foreground disabled:cursor-not-allowed"
                  >
                    {lbl}
                  </button>
                ))}
              </div>
            }
          />
        }
        emptyState={{
          title: query ? `No resources match "${query}".` : "No resources found.",
        }}
      />
    </div>
  )
}
