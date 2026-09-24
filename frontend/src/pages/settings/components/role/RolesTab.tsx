import { useState } from 'react'
import { Lock } from 'lucide-react'

import { usePermissions } from '@/core/hooks/usePermissions'
import { useRoles } from '@/core/hooks/useRoles'
import { RolesHeader } from './list/roles-header'
import { RolesTable } from './list/roles-table'
import { RoleDetailContent } from './detail/role-detail-content'

// undefined = list, null = creating new, string = editing existing
type View = undefined | null | string

export default function RolesTab() {
  const [view, setView] = useState<View>(undefined)
  const { hasPermission } = usePermissions()
  const canWrite = hasPermission('role:write')
  const { roles, loading, error, refetch } = useRoles()

  if (view !== undefined) {
    return (
      // Break out of the settings content padding and fill the viewport height
      // so the detail layout's flex column gets a fixed height to work against.
      <div className="-mx-4 -my-4 lg:-mx-12 lg:-my-8 h-[calc(100svh-var(--header-height))] flex flex-col">
        <RoleDetailContent
          roleId={view ?? ''}
          onBack={() => setView(undefined)}
        />
      </div>
    )
  }

  if (loading) {
    return <div className="p-8 text-center text-muted-foreground text-sm">Loading roles…</div>
  }

  if (error) {
    return (
      <div className="p-8 text-center text-sm text-destructive">
        {error}
        <button
          onClick={() => refetch()}
          className="ml-2 underline cursor-pointer bg-transparent border-none text-cobalt"
        >
          Retry
        </button>
      </div>
    )
  }

  const totalMembers = roles.reduce((sum, r) => sum + r.user_count, 0)

  return (
    <div>
      <RolesHeader
        totalRoles={roles.length}
        totalMembers={totalMembers}
        onRefresh={() => refetch()}
        onCreate={() => setView(null)}
        canWrite={canWrite}
      />
      {!canWrite && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-warning/30 bg-warning-subtle p-3 text-sm text-warning">
          <Lock className="h-4 w-4 shrink-0" />
          You have read-only access to Roles. Contact an admin to make changes.
        </div>
      )}
      <RolesTable roles={roles} onSelectRole={setView} />
    </div>
  )
}
