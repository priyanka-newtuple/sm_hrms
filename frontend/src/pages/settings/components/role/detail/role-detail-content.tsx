import { useState, useEffect, useMemo, useRef } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Lock } from "lucide-react"
import { toast } from "sonner"

import { type Role } from "@/lib/roles-data"
import { isEntityFilterComplete, type EntityFilter, type FieldPermission } from "@/lib/entity-data"
import { roles as rolesApi } from "@/core/services/api"
import ConfirmDialog from "@/core/components/ConfirmDialog"
import { usePermissions } from "@/core/hooks/usePermissions"
import { useEntityTypes } from "@/core/hooks/useEntityTypes"
import { roleKeys } from "@/core/services/api/queryKeys"
import { buildRolePayload, readEntityFilter } from "./role-payload"
import { RoleDetailHeader } from "./role-detail-header"
import { TabBar } from "./tab-bar"
import { DisplayTab } from "./display-tab"
import { PermissionsTab } from "./permissions-tab"
import { RoleDetailFooter } from "./role-detail-footer"
import { EntityAccessTab } from "../entity-access-tab"
import { FieldPermissionTab } from "../field-permission-tab"
import { FormsTab } from "../forms-tab"
import { TransitionsTab } from "./transitions-tab"

const TABS = [
  { id: "display", label: "Display" },
  { id: "permissions", label: "Permissions" },
  { id: "entity", label: "Entity Access" },
  { id: "field-permission", label: "Field Filteration" },
  { id: "forms", label: "Forms" },
  { id: "transitions", label: "Workflows & Transitions" },
]

const SYSTEM_ENTITY_ACTIONS = ["view", "create", "edit", "delete"] as const

const DEFAULT_NEW_ROLE: Role = {
  id: '',
  name: 'new_role',
  display_name: 'New Role',
  description: null,
  is_system: false,
  priority: 50,
  color: '#4F46E5',
  user_count: 0,
}

interface RoleDetailContentProps {
  roleId: string
  onBack: () => void
}

export function RoleDetailContent({ roleId, onBack }: RoleDetailContentProps) {
  const isNew = !roleId
  const qc = useQueryClient()
  const baselineSnapshotRef = useRef<string | null>(null)
  const { hasPermission } = usePermissions()
  const canWrite = hasPermission('role:write')
  const { entityTypes, loading: entityTypesLoading, error: entityTypesError } = useEntityTypes()

  const { data: loadedRole, isLoading, error: loadError } = useQuery({
    queryKey: roleKeys.detail(roleId),
    queryFn: () => rolesApi.get(roleId),
    enabled: !isNew,
  })

  const [activeTab, setActiveTab] = useState("display")
  const [role, setRole] = useState<Role>(DEFAULT_NEW_ROLE)
  const [granted, setGranted] = useState<Set<string>>(() => new Set())
  const [entityPerms, setEntityPerms] = useState<Set<string>>(() => new Set())
  const [fieldPerms, setFieldPerms] = useState<Record<string, FieldPermission>>({})
  // entity_type -> read-narrowing condition on that entity type's `view` permission
  // (entity field permission filter) — one expression per entity type, per role.
  const [entityConditions, setEntityConditions] = useState<Record<string, EntityFilter>>({})
  const [transitionPerms, setTransitionPerms] = useState<Set<string>>(() => new Set())
  const [workflowPerms, setWorkflowPerms] = useState<Set<string>>(() => new Set())
  const [workflowRestricted, setWorkflowRestricted] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [initialized, setInitialized] = useState(isNew)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  const snapshot = useMemo(
    () =>
      JSON.stringify({
        role,
        granted: Array.from(granted).sort(),
        entityPerms: Array.from(entityPerms).sort(),
        fieldPerms: Object.entries(fieldPerms).sort(([a], [b]) => a.localeCompare(b)),
        entityConditions: Object.entries(entityConditions).sort(([a], [b]) => a.localeCompare(b)),
        transitionPerms: Array.from(transitionPerms).sort(),
        workflowPerms: Array.from(workflowPerms).sort(),
        workflowRestricted,
      }),
    [role, granted, entityPerms, fieldPerms, entityConditions, transitionPerms, workflowPerms, workflowRestricted]
  )

  // Seed form state from loaded role
  useEffect(() => {
    if (!loadedRole) return
    const nextRole = {
      id: loadedRole.id,
      name: loadedRole.name,
      display_name: loadedRole.display_name,
      description: loadedRole.description,
      is_system: loadedRole.is_system,
      priority: loadedRole.priority,
      color: loadedRole.color ?? '#4F46E5',
      user_count: loadedRole.user_count ?? 0,
    }

    const nextEntityPerms = new Set<string>()
    if (loadedRole.is_system) {
      // System roles receive every entity action implicitly in the backend.
      // Their role record therefore has no explicit permission rows to load,
      // but the editor must display the effective access rather than an empty
      // (and misleadingly editable) matrix.
      entityTypes.forEach((entityType) => {
        SYSTEM_ENTITY_ACTIONS.forEach((action) => {
          nextEntityPerms.add(`${entityType.name}:${action}`)
        })
      })
    } else {
      loadedRole.entity_permissions.forEach((p) => {
        if (p.allowed) nextEntityPerms.add(`${p.entity_type}:${p.action}`)
      })
    }

    const nextFieldPerms: Record<string, FieldPermission> = {}
    loadedRole.field_permissions.forEach((p) => {
      nextFieldPerms[`${p.entity_type}:${p.field_name}`] = {
        view: p.can_view,
        edit: p.can_edit,
        mask: p.mask_value,
      }
    })

    // Only the `view` action's condition fields are surfaced — writes are
    // never condition-gated, so a condition on any other action would be
    // inert and isn't something the Field Permission tab exposes.
    const nextEntityConditions: Record<string, EntityFilter> = {}
    loadedRole.entity_permissions.forEach((p) => {
      const filter = readEntityFilter(p)
      if (filter) nextEntityConditions[p.entity_type] = filter
    })

    const nextGranted = new Set(loadedRole.permissions.map((p) => p.permission_key))

    const nextTransitionPerms = new Set<string>(
      (loadedRole.transition_permissions ?? []).map(
        (p) => `${p.machine_name}:${p.transition_key}`
      )
    )
    const nextWorkflowPerms = new Set<string>(
      (loadedRole.workflow_permissions ?? []).map((p) => p.machine_name)
    )

    baselineSnapshotRef.current = JSON.stringify({
      role: nextRole,
      granted: Array.from(nextGranted).sort(),
      entityPerms: Array.from(nextEntityPerms).sort(),
      fieldPerms: Object.entries(nextFieldPerms).sort(([a], [b]) => a.localeCompare(b)),
      entityConditions: Object.entries(nextEntityConditions).sort(([a], [b]) => a.localeCompare(b)),
      transitionPerms: Array.from(nextTransitionPerms).sort(),
      workflowPerms: Array.from(nextWorkflowPerms).sort(),
      workflowRestricted: nextWorkflowPerms.size > 0,
    })

    setRole(nextRole)
    setEntityPerms(nextEntityPerms)
    setFieldPerms(nextFieldPerms)
    setEntityConditions(nextEntityConditions)
    setGranted(nextGranted)
    setTransitionPerms(nextTransitionPerms)
    setWorkflowPerms(nextWorkflowPerms)
    setWorkflowRestricted(nextWorkflowPerms.size > 0)
    setDirty(false)
    setInitialized(true)
  }, [entityTypes, loadedRole])

  // Establish a clean baseline for new roles.
  useEffect(() => {
    if (!isNew || baselineSnapshotRef.current) return
    baselineSnapshotRef.current = snapshot
    setDirty(false)
  }, [isNew, snapshot])

  // Track dirty state against the last loaded/saved baseline.
  useEffect(() => {
    if (!initialized || !baselineSnapshotRef.current) return
    setDirty(snapshot !== baselineSnapshotRef.current)
  }, [initialized, snapshot])

  const deleteMutation = useMutation({
    mutationFn: () => rolesApi.delete(roleId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: roleKeys.list() })
      onBack()
    },
    onError: (err: Error) => {
      toast.error(err.message ?? 'Failed to delete role')
    },
  })

  // Guard against resubmitting entity/field permissions for entity types the
  // org no longer has (e.g. renamed/removed after this role was created —
  // those rows are invisible in Entity Access/Forms, so the UI can't let the
  // admin fix them, yet they'd otherwise get silently resent on every save
  // and rejected by the backend). Only filter once the entity-types list has
  // genuinely, successfully loaded — never filter against an empty/still
  // -loading/errored list, since that would silently wipe out *legitimate*
  // permissions instead of just dropping stale ones.
  const knownEntityTypeNames = useMemo(
    () => new Set(entityTypes.map((e) => e.name)),
    [entityTypes]
  )
  const canDropStaleEntityTypes =
    !entityTypesLoading && !entityTypesError && knownEntityTypeNames.size > 0
  const isKnownEntityType = (name: string) =>
    !canDropStaleEntityTypes || knownEntityTypeNames.has(name)

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!canWrite) return
      const { payload, staleEntityTypes } = buildRolePayload({
        granted,
        entityPerms,
        entityConditions,
        fieldPerms,
        transitionPerms,
        workflowPerms: workflowRestricted ? workflowPerms : new Set(),
        isKnownEntityType,
      })

      if (staleEntityTypes.length > 0) {
        toast.warning('Removed permissions for entity types no longer in this organization', {
          description: staleEntityTypes.join(', '),
        })
      }

      if (isNew) {
        await rolesApi.create({
          name: role.name,
          display_name: role.display_name,
          description: role.description || undefined,
          priority: role.priority,
          color: role.color,
          ...payload,
        })
      } else {
        await rolesApi.update(roleId, {
          name: role.name,
          display_name: role.display_name,
          description: role.description || undefined,
          color: role.color,
          // system roles block priority, permissions, and field_permissions changes
          ...(!role.is_system && {
            priority: role.priority,
            ...payload,
          }),
        })
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: roleKeys.list() })
      if (!isNew) qc.invalidateQueries({ queryKey: roleKeys.detail(roleId) })
      baselineSnapshotRef.current = snapshot
      setDirty(false)
      toast.success(isNew ? 'Role created' : 'Role saved')
      if (isNew) onBack()
    },
    onError: (e) => {
      toast.error('Failed to save role', { description: e instanceof Error ? e.message : undefined })
    },
  })

  if (!isNew && isLoading) {
    return (
      <div className="p-12 text-center text-muted-foreground text-sm">Loading role…</div>
    )
  }

  if (!isNew && (loadError || (!isLoading && !loadedRole))) {
    return (
      <div className="p-12 text-center text-muted-foreground text-sm">
        Role not found.{" "}
        <button
          onClick={onBack}
          className="underline cursor-pointer bg-transparent border-none text-cobalt"
        >
          Back to roles
        </button>
      </div>
    )
  }

  const permCount = granted.size

  const tabs = TABS.map((t) => {
    if (t.id === "permissions") return { ...t, badge: permCount }
    if (t.id === "transitions" && transitionPerms.size > 0) return { ...t, badge: transitionPerms.size }
    return t
  })

  return (
    <div className="bg-background flex flex-col h-full">
      <div className="flex-1 overflow-y-auto">
        <div className="px-10 py-[26px] pb-10 w-full">
          <RoleDetailHeader role={role} onBack={onBack} onDelete={() => setShowDeleteConfirm(true)} isNew={isNew} canWrite={canWrite} />
          <TabBar tabs={tabs} activeTab={activeTab} onTabChange={setActiveTab} />

          {!canWrite && (
            <div className="mb-4 flex items-center gap-2 rounded-lg border border-warning/30 bg-warning-subtle p-3 text-sm text-warning">
              <Lock className="h-4 w-4 shrink-0" />
              You have read-only access to Roles. Contact an admin to make changes.
            </div>
          )}

          {activeTab === "display" && (
            <DisplayTab role={role} setRole={setRole} disabled={!canWrite} />
          )}
          {activeTab === "permissions" && (
            <PermissionsTab
              role={role}
              granted={granted}
              setGranted={setGranted}
              disabled={!canWrite || role.is_system}
            />
          )}
          {activeTab === "entity" && (
            <EntityAccessTab
              role={role}
              entityPerms={entityPerms}
              setEntityPerms={setEntityPerms}
              disabled={!canWrite || role.is_system}
            />
          )}
          {activeTab === "field-permission" && (
            <FieldPermissionTab
              role={role}
              entityConditions={entityConditions}
              setEntityConditions={setEntityConditions}
              entityPerms={entityPerms}
              disabled={!canWrite || role.is_system}
            />
          )}
          {activeTab === "forms" && (
            <FormsTab
              role={role}
              fieldPerms={fieldPerms}
              setFieldPerms={setFieldPerms}
              entityPerms={entityPerms}
              disabled={!canWrite || role.is_system}
            />
          )}
          {activeTab === "transitions" && (
            <TransitionsTab
              transitionPerms={transitionPerms}
              onChange={setTransitionPerms}
              workflowPerms={workflowPerms}
              workflowRestricted={workflowRestricted}
              onWorkflowPermsChange={setWorkflowPerms}
              onWorkflowRestrictedChange={(restricted) => {
                setWorkflowRestricted(restricted)
                if (!restricted) setWorkflowPerms(new Set())
              }}
              roleColor={role.color}
              disabled={!canWrite}
            />
          )}
        </div>
      </div>

      <ConfirmDialog
        open={showDeleteConfirm}
        title="Delete Role?"
        message={`Are you sure you want to delete "${role.display_name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        variant="danger"
        loading={deleteMutation.isPending}
        onConfirm={() => {
          if (!canWrite) return
          deleteMutation.mutate()
        }}
        onClose={() => setShowDeleteConfirm(false)}
      />

      <RoleDetailFooter
        dirty={dirty}
        isSaving={saveMutation.isPending}
        canSave={
          role.name.trim().length > 0 &&
          role.display_name.trim().length > 0 &&
          Object.values(entityConditions).every(isEntityFilterComplete) &&
          (!workflowRestricted || workflowPerms.size > 0)
        }
        onSave={() => {
          if (!canWrite) return
          saveMutation.mutate()
        }}
        onCancel={onBack}
        canWrite={canWrite}
      />
    </div>
  )
}
