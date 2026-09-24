import {
  Activity,
  BarChart3,
  CalendarClock,
  Boxes,
  Building2,
  FileText,
  Filter,
  FolderOpen,
  Key,
  Layers,
  Link,
  Mail,
  MonitorCog,
  Palette,
  Play,
  Columns3,
  Rows3,
  ScrollText,
  Server,
  Shield,
  Sparkles,
  Type,
  Users,
  Wrench,
} from 'lucide-react';

import type { SettingsTabConfig, SettingsTabGroup } from '../components/SettingsSidebar';
import type { SettingsTab } from '..';

export const VALID_TABS = [
  'funnels',
  'fields',
  'methods',
  'automations',
  'agents',
  'agent_runs',
  'mcp_tools',
  'entities',
  'forms',
  'email_templates',
  'connectors',
  'documents',
  'integrations',
  'users',
  'roles',
  'logs',
  'branding',
  'display',
  'analytics',
  'column_labels',
  'global_filter',
  'app_labels',
  'organizations',
  'traces',
  'coverage',
] as const;

/**
 * Tabs the platform hides unless the active skin opts into them.
 *
 * The Field and Method libraries are surfaces for deployments that compose
 * forms from a shared, versioned library of fields. A deployment that doesn't
 * work that way has no use for them, so they are off by default and a skin
 * turns them on via `SkinManifest.optionalSettingsTabs`.
 */
export const OPTIONAL_SETTINGS_TABS = ['fields', 'methods'] as const satisfies readonly SettingsTab[];

/**
 * Backend permission resources that belong to optional Settings tabs.
 *
 * Keep this mapping beside the tab gate so a skin that does not expose a
 * library also does not expose controls for granting that library's access.
 * This is deliberately a UI concern only; the backend continues to define and
 * enforce these permissions for every deployment.
 */
const OPTIONAL_SETTINGS_TAB_PERMISSION_RESOURCES: Partial<Record<SettingsTab, string>> = {
  fields: 'field_library',
  methods: 'method_library',
};

/** Whether a permission resource should be visible for the active skin. */
export function isOptionalPermissionResourceVisible(
  resource: string,
  optionalTabs: readonly string[] = [],
): boolean {
  const gatedTab = OPTIONAL_SETTINGS_TABS.find(
    (tab) => OPTIONAL_SETTINGS_TAB_PERMISSION_RESOURCES[tab] === resource,
  );
  return !gatedTab || optionalTabs.includes(gatedTab);
}

/**
 * Every settings tab, minus the optional ones this skin hasn't opted into.
 *
 * Filtering here rather than at the render site is deliberate: the caller uses
 * this same list to resolve a `?tab=` deep link, so a tab dropped here is
 * unreachable by URL as well as absent from the sidebar.
 */
export function getTabGroups(
  optionalTabs: readonly string[] = [],
): SettingsTabGroup<SettingsTab>[] {
  const enabled = new Set(optionalTabs);
  return withOptionalTabs(allTabGroups(), enabled);
}

function withOptionalTabs(
  groups: SettingsTabGroup<SettingsTab>[],
  enabled: Set<string>,
): SettingsTabGroup<SettingsTab>[] {
  const isGated = (id: string) => (OPTIONAL_SETTINGS_TABS as readonly string[]).includes(id);
  return groups
    .map((group) => ({
      ...group,
      tabs: group.tabs.filter((tab) => {
        // The public route is now `forms`, while existing skin manifests keep
        // using the internal `methods` feature key that enables this library.
        const featureId = tab.id === 'forms' ? 'methods' : tab.id;
        return !isGated(featureId) || enabled.has(featureId);
      }),
    }))
    .filter((group) => group.tabs.length > 0);
}

function allTabGroups(): SettingsTabGroup<SettingsTab>[] {
  return [
    {
      label: 'Build',
      tabs: [
        { id: 'funnels', label: 'Funnels', icon: Layers, permission: 'workflow:read' },
        { id: 'entities',        label: 'Entities',        icon: Boxes,    permission: 'entity_record:read' },
        { id: 'fields', label: 'Fields', icon: Rows3, permission: 'field_library:read' },
        { id: 'forms', label: 'Forms', icon: FileText, permission: 'method_library:read' },
        { id: 'automations', label: 'Automations', icon: CalendarClock, permission: 'workflow:read' },
        { id: 'email_templates', label: 'Email Templates', icon: Mail,     permission: 'email_template:read' },
      ],
    },
    {
      label: 'Run',
      tabs: [
        { id: 'agents', label: 'Agents', icon: Sparkles, permission: 'agent:read' },
        { id: 'mcp_tools', label: 'MCP Tools', icon: Wrench, permission: 'agent:read' },
        { id: 'agent_runs', label: 'Agent Runs', icon: Play, permission: 'agent:read' },
        { id: 'traces', label: 'Agent Traces', icon: Activity, permission: 'agent_trace:read' },
        { id: 'coverage', label: 'API Coverage', icon: Server, permission: 'api_coverage:read' },
      ],
    },
    {
      label: 'Data',
      tabs: [
        { id: 'documents',    label: 'Documents',    icon: FolderOpen, permission: 'file:read' },
        { id: 'integrations', label: 'Integrations', icon: Key,        permission: 'integration:read' },
        { id: 'connectors',   label: 'Connectors',   icon: Link,       permission: 'entity_record:read' },
      ],
    },
    {
      label: 'Govern',
      tabs: [
        { id: 'users', label: 'Users', icon: Users, permission: 'user:read' },
        { id: 'roles', label: 'Roles', icon: Shield, permission: 'role:read' },
        { id: 'logs', label: 'Logs', icon: ScrollText, permission: 'logs:read' },
        { id: 'branding', label: 'Branding', icon: Palette, permission: 'metadata:read' },
        { id: 'display', label: 'Display', icon: MonitorCog, permission: 'metadata:read' },
        { id: 'analytics', label: 'Analytics', icon: BarChart3, permission: 'analytics:read' },
        { id: 'column_labels', label: 'Column Labels', icon: Columns3, permission: 'metadata:read' },
        { id: 'global_filter', label: 'Global Filter', icon: Filter, permission: 'metadata:read' },
        { id: 'app_labels', label: 'App Labels', icon: Type, permission: 'metadata:read' },
        { id: 'organizations', label: 'Organizations', icon: Building2, superAdminOnly: true },
      ],
    },
  ];
}

export function filterTabGroupsByPermission(
  groups: SettingsTabGroup<SettingsTab>[],
  hasPermission: (permission: string) => boolean,
  isSuperAdmin: boolean,
): SettingsTabGroup<SettingsTab>[] {
  return groups
    .map((group) => ({
      ...group,
      tabs: group.tabs.filter((tab) => isTabVisible(tab, hasPermission, isSuperAdmin)),
    }))
    .filter((group) => group.tabs.length > 0);
}

export function isTabVisible(
  tab: Pick<SettingsTabConfig, 'permission' | 'superAdminOnly'>,
  hasPermission: (permission: string) => boolean,
  isSuperAdmin: boolean,
): boolean {
  if (tab.superAdminOnly && !isSuperAdmin) return false;
  if (tab.permission && !hasPermission(tab.permission)) return false;
  return true;
}
