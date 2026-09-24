import { lazy, Suspense } from 'react';
import { Settings2 } from 'lucide-react';
import { Navigate, useSearchParams } from 'react-router-dom';

import { useAuth } from '../../core/auth';
import EmptyState from '../../core/components/EmptyState';
import PermissionDenied from '../../core/components/PermissionDenied';
import { SkeletonPage } from '../../core/components/Skeleton';
import { usePermissions } from '../../core/hooks/usePermissions';
import SettingsSidebar from './components/SettingsSidebar';

import { filterTabGroupsByPermission, getTabGroups, isTabVisible, VALID_TABS } from './lib/constant';
import { useSkin } from '@/skins/SkinContext';
import { isSuperAdminUser } from '../../core/utils';


export type SettingsTab = (typeof VALID_TABS)[number];

// Only one tab is ever visible at a time — lazy-load each so visiting
// Settings doesn't pull in every tab (including a full Tiptap editor for
// email templates) regardless of which section is actually opened.
const TAB_COMPONENTS: Partial<Record<SettingsTab, React.ComponentType>> = {
  funnels: lazy(() => import('./components/funnels/FunnelsTab')),
  fields: lazy(() => import('./components/fields/FieldsTab')),
  forms: lazy(() => import('./components/methods/MethodsTab')),
  automations: lazy(() => import('./components/automations/AutomationsTab')),
  agents: lazy(() => import('./components/agents/AgentsTab')),
  agent_runs: lazy(() => import('./components/agents/AgentRunConsole')),
  mcp_tools: lazy(() => import('./components/agents/McpToolsTab')),
  entities: lazy(() => import('./components/entity-types/EntityTypesTab')),
  email_templates: lazy(() =>
    import('./components/email-template').then((m) => ({ default: m.EmailTemplateApp })),
  ),
  connectors: lazy(() => import('./components/connectors/ConnectorsTab')),
  documents: lazy(() => import('./components/document-types/DocumentTypesTab')),
  integrations: lazy(() => import('./components/integrations/IntegrationsTab')),
  coverage: lazy(() => import('./components/platform/ApiCoverageTab')),
  users: lazy(() => import('./components/users/UsersTab')),
  roles: lazy(() => import('./components/role/RolesTab')),
  logs: lazy(() => import('./components/logs/LogsTab')),
  branding: lazy(() => import('./components/branding/BrandingTab')),
  display: lazy(() => import('./components/display/DisplayTab')),
  analytics: lazy(() => import('./components/analytics/AnalyticsTab')),
  column_labels: lazy(() => import('./components/column-labels/ColumnLabelsTab')),
  global_filter: lazy(() => import('./components/global-filter/GlobalFilterTab')),
  app_labels: lazy(() => import('./components/app-labels/AppLabelsTab')),
  traces: lazy(() => import('./components/agents/AgentTracesTab')),
  organizations: lazy(() => import('./components/organizations/OrganizationsTab')),
};

export default function SettingsPage() {
  const { user } = useAuth();
  const { hasPermission } = usePermissions();
  const { skin } = useSkin();
  const [searchParams, setSearchParams] = useSearchParams();

  if (!hasPermission('settings:access')) {
    return <Navigate to="/dashboard" replace />;
  }

  const isSuperAdmin = isSuperAdminUser(user);
  // Library sections are off unless this deployment's skin asks for them, so a
  // platform install never shows a section it has no use for.
  const allGroups = getTabGroups(skin.optionalSettingsTabs);
  const visibleGroups = filterTabGroupsByPermission(allGroups, hasPermission, isSuperAdmin);
  const visibleTabs = visibleGroups.flatMap((group) => group.tabs);
  const firstVisibleTab = visibleTabs[0]?.id ?? null;

  const rawTab = searchParams.get('tab') as SettingsTab | null;
  const isKnownTab = rawTab ? VALID_TABS.includes(rawTab) : false;
  const requestedTab = isKnownTab ? rawTab : null;
  const allowedRequestedTab = requestedTab
    ? visibleTabs.find(
        (tab) => tab.id === requestedTab && isTabVisible(tab, hasPermission, isSuperAdmin),
      )
    : null;
  const activeTab: SettingsTab | null = allowedRequestedTab?.id ?? firstVisibleTab;

  const handleTabChange = (tab: SettingsTab) => {
    setSearchParams({ tab }, { replace: true });
  };

  const ActiveComponent = activeTab ? TAB_COMPONENTS[activeTab] : null;

  if (rawTab === 'methods') {
    return <Navigate to="/settings?tab=forms" replace />;
  }

  if (rawTab && !isKnownTab && firstVisibleTab) {
    return <Navigate to={`/settings?tab=${firstVisibleTab}`} replace />;
  }

  return (
    <div className="-mx-4 -my-4 lg:-mx-12 lg:-my-8 flex min-h-[calc(100svh-var(--header-height))]">
      <aside className="sticky top-[var(--header-height)] h-[calc(100svh-var(--header-height))] overflow-y-auto shrink-0">
        <SettingsSidebar
          groups={visibleGroups}
          activeTab={requestedTab && !allowedRequestedTab ? null : activeTab}
          onTabChange={handleTabChange}
        />
      </aside>

      <div className="flex-1 min-w-0 overflow-y-auto p-4 lg:p-6">
        {visibleTabs.length === 0 ? (
          <EmptyState
            surface="panel"
            icon={
              <div className="rounded-2xl bg-muted p-4 text-muted-foreground">
                <Settings2 className="h-8 w-8" />
              </div>
            }
            title="No settings available"
            description="Your account can access Settings, but no settings sections are currently assigned to you."
          />
        ) : requestedTab && !allowedRequestedTab ? (
          <div className="rounded-2xl border border-border bg-card p-8">
            <PermissionDenied message="You do not have read access to this settings section." />
          </div>
        ) : (
          ActiveComponent && (
            <Suspense fallback={<SkeletonPage />}>
              <ActiveComponent />
            </Suspense>
          )
        )}
      </div>
    </div>
  );
}
