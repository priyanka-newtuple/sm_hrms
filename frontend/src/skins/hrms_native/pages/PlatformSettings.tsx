import OrganizationSettings from './OrganizationSettings';
import { Building2 } from 'lucide-react';
import { lazy, Suspense, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useHrmsCapabilities } from '../capabilities';
import { usePermissions } from '../../../core/hooks/usePermissions';
import SettingsSidebar from '../../../pages/settings/components/SettingsSidebar';
import { getTabGroups, filterTabGroupsByPermission } from '../../../pages/settings/lib/constant';
import type { SettingsTab } from '../../../pages/settings';
import { PageHero } from '../components/PageHero';



export function ConfigurationGuard({children}: {children: ReactNode}) {
  const caps = useHrmsCapabilities();
  if (caps.isLoading) return <p className="p-6">Loading settings permissions…</p>;
  if (!caps.data?.capabilities.includes('platform:configure')) return <p role="alert" className="p-6">Settings are available only to Super Admin.</p>;
  return <>{children}</>;
}

const TAB_COMPONENTS: Partial<Record<SettingsTab, React.ComponentType>> = {
  funnels: lazy(() => import('../../../pages/settings/components/funnels/FunnelsTab')),
  fields: lazy(() => import('../../../pages/settings/components/fields/FieldsTab')),
  // `forms` is the platform's public route for the Method Library, not the legacy Form Configuration.
  forms: lazy(() => import('../../../pages/settings/components/methods/MethodsTab')),
  automations: lazy(() => import('../../../pages/settings/components/automations/AutomationsTab')),
  agents: lazy(() => import('../../../pages/settings/components/agents/AgentsTab')),
  agent_runs: lazy(() => import('../../../pages/settings/components/agents/AgentRunConsole')),
  mcp_tools: lazy(() => import('../../../pages/settings/components/agents/McpToolsTab')),
  entities: lazy(() => import('../../../pages/settings/components/entity-types/EntityTypesTab')),
  email_templates: lazy(() =>
    import('../../../pages/settings/components/email-template').then((m) => ({ default: m.EmailTemplateApp })),
  ),
  connectors: lazy(() => import('../../../pages/settings/components/connectors/ConnectorsTab')),
  documents: lazy(() => import('../../../pages/settings/components/document-types/DocumentTypesTab')),
  integrations: lazy(() => import('../../../pages/settings/components/integrations/IntegrationsTab')),
  coverage: lazy(() => import('../../../pages/settings/components/platform/ApiCoverageTab')),
  users: lazy(() => import('../../../pages/settings/components/users/UsersTab')),
  roles: lazy(() => import('../../../pages/settings/components/role/RolesTab')),
  logs: lazy(() => import('../../../pages/settings/components/logs/LogsTab')),
  branding: lazy(() => import('../../../pages/settings/components/branding/BrandingTab')),
  display: lazy(() => import('../../../pages/settings/components/display/DisplayTab')),
  analytics: lazy(() => import('../../../pages/settings/components/analytics/AnalyticsTab')),
  column_labels: lazy(() => import('../../../pages/settings/components/column-labels/ColumnLabelsTab')),
  global_filter: lazy(() => import('../../../pages/settings/components/global-filter/GlobalFilterTab')),
  app_labels: lazy(() => import('../../../pages/settings/components/app-labels/AppLabelsTab')),
  traces: lazy(() => import('../../../pages/settings/components/agents/AgentTracesTab')),
  organizations: OrganizationSettings,
};
export default function PlatformSettings() {
  const [params, setParams] = useSearchParams();
  const { hasPermission } = usePermissions();
  // Tenant Super Admin must not acquire platform-wide organization administration.
  const groups = filterTabGroupsByPermission(getTabGroups(['fields', 'methods']), hasPermission, false);
  groups.unshift({label: 'Workspace', tabs: [{id: 'organizations', label: 'Organization', icon: Building2}]});
  const requested = params.get('tab') ?? 'organizations';
  const active = groups.flatMap(g => g.tabs).find(t => t.id === requested)?.id as SettingsTab | undefined;
  const Component = active ? TAB_COMPONENTS[active] : undefined;
  return <ConfigurationGuard><div className="hrms-ws-page hrms-settings-page">
    <PageHero compact title="Settings" intro="Organization, people, roles, forms and workflows for this HRMS tenant." illustration="settings" />
    <section className="hrms-settings-frame flex min-w-0 bg-background">
    <SettingsSidebar groups={groups} activeTab={active ?? null} onTabChange={tab => setParams({tab})} />
    <div className="min-w-0 flex-1 p-6"><Suspense fallback={<p>Loading configuration…</p>}>
      {Component ? <Component /> : <p role="alert">This settings section is not available in your organization.</p>}
    </Suspense></div>
  </section></div></ConfigurationGuard>;
}
