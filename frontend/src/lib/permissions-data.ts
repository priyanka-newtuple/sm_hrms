export type Action = string

export const ACTION_RANK: Record<string, number> = {
  read:   1,
  write:  2,
  access: 3,
}

export interface PermissionDefinition {
  key: string
  resource: string
  action: string
  description: string
}

function formatLabel(resource: string): string {
  return resource.split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}

const RESOURCE_PRESENTATION_OVERRIDES: Record<
  string,
  { label: string; blurb: string }
> = {
  method_library: {
    label: 'Forms',
    blurb: 'View forms and form categories',
  },
}

export interface PermissionsConfig {
  RESOURCE_META:      Record<string, { label: string; blurb: string }>
  RESOURCE_ACTIONS:   Record<string, string[]>
  RESOURCES:          string[]
  ALL_ACTIONS:        string[]
  ALL_PERMISSION_KEYS: string[]
  PERMISSION_PRESETS: {
    none:   () => Set<string>
    read:   () => Set<string>
    editor: () => Set<string>
    full:   () => Set<string>
  }
}

export function buildPermissionsConfig(defs: PermissionDefinition[]): PermissionsConfig {
  const resourceMeta: Record<string, { label: string; blurb: string }> = {}
  const resourceActions: Record<string, string[]> = {}
  const allActionsSet = new Set<string>()

  for (const def of defs) {
    const presentationOverride = RESOURCE_PRESENTATION_OVERRIDES[def.resource]
    if (!resourceMeta[def.resource]) {
      resourceMeta[def.resource] = presentationOverride ?? {
        label: formatLabel(def.resource),
        blurb: def.description,
      }
    } else if (def.action === 'read') {
      resourceMeta[def.resource].blurb = presentationOverride?.blurb ?? def.description
    }

    if (!resourceActions[def.resource]) resourceActions[def.resource] = []
    if (!resourceActions[def.resource].includes(def.action)) {
      resourceActions[def.resource].push(def.action)
    }
    allActionsSet.add(def.action)
  }

  const rankOf = (a: string) => ACTION_RANK[a] ?? 99
  for (const r of Object.keys(resourceActions)) {
    resourceActions[r].sort((a, b) => rankOf(a) - rankOf(b))
  }

  const resources = Object.keys(resourceActions)
  const allKeys = resources.flatMap((r) => resourceActions[r].map((a) => `${r}:${a}`))
  const allActions = Array.from(allActionsSet).sort((a, b) => rankOf(a) - rankOf(b))
  const makeSet = (keys: string[]) => new Set(keys)

  return {
    RESOURCE_META: resourceMeta,
    RESOURCE_ACTIONS: resourceActions,
    RESOURCES: resources,
    ALL_ACTIONS: allActions,
    ALL_PERMISSION_KEYS: allKeys,
    PERMISSION_PRESETS: {
      none:   () => makeSet([]),
      read:   () => makeSet(allKeys.filter((k) => k.endsWith(':read'))),
      editor: () => makeSet(allKeys),
      full:   () => makeSet(allKeys),
    },
  }
}
