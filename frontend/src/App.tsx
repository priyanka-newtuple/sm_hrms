import { lazy, Suspense } from 'react';
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom';
import { Loader2 } from 'lucide-react';

import { AuthProvider, ProtectedRoute } from './core/auth';
import { OrgSelectorProvider } from './core/contexts/OrgSelectorContext';
import { GlobalEntityFilterProvider } from './core/contexts/GlobalEntityFilterContext';
import OrgDocumentHead from './core/components/OrgDocumentHead';
import { AgentProvider } from './core/agent';
import { useFeatureFlags } from './core/hooks/useFeatureFlags';
import { SkeletonPage } from './core/components/Skeleton';
import AppLayout from './layouts/App-Layout';
import { resolveActiveSkin } from './skins/registry';
import { useSkin } from './skins';
import { useWorkflows } from './shared/hooks/useWorkflows';
import { resolveSkinHomePath } from './shared/skin/homePath';

// Route-level code splitting: each page ships as its own chunk, loaded only
// when its route is visited, instead of all 18 pages bundling into one
// multi-MB chunk on every first load regardless of which page is landed on.
const SettingsPage = lazy(() => import('./pages/settings'));
const LoginPage = lazy(() => import('./pages/auth/LoginPage'));
const GoogleCallbackPage = lazy(() => import('./pages/auth/GoogleCallbackPage'));
const MicrosoftCallbackPage = lazy(() => import('./pages/auth/MicrosoftCallbackPage'));
const RemoteMcpCallbackPage = lazy(() => import('./pages/auth/RemoteMcpCallbackPage'));
const GoogleCalendarCallbackPage = lazy(() => import('./pages/GoogleCalendarCallbackPage'));
const PendingApprovalPage = lazy(() => import('./pages/auth/PendingApprovalPage'));
const PendingOrgApprovalPage = lazy(() => import('./pages/auth/PendingOrgApprovalPage'));
const AcceptInvitePage = lazy(() => import('./pages/auth/AcceptInvitePage'));
const ForgotPasswordPage = lazy(() => import('./pages/auth/Forgot-Password'));
const ResetPasswordPage = lazy(() => import('./pages/auth/Reset-Password'));
const PipelinePage = lazy(() => import('./pages/Pipeline'));
const EntityDetailPage = lazy(() => import('./pages/Pipeline/EntityDetailPage'));
const WorkflowsPage = lazy(() => import('./pages/Workflows'));
const FunnelEditorPage = lazy(() => import('./pages/funnel'));
const RecordDetailPage = lazy(() => import('./pages/records/detail'));
const RecordsPage = lazy(() => import('./pages/records'));
const DashboardPage = lazy(() => import('./pages/dashboard'));
const ChangelogsPage = lazy(() => import('./pages/Changelogs'));
const PublicFormPage = lazy(() => import('./pages/publicform/index'));
const AgentModePage = lazy(() => import('./pages/agent/AgentModePage'));
const BulkImportPage = lazy(() => import('./pages/bulk-import'));

// Resolve the active skin synchronously at module level (same approach as SkinContext).
// customPages are injected directly into the React Router tree so they land inside
// the protected AppLayout without any runtime overhead.
const SKIN_ID = (import.meta.env.VITE_SKIN_ID as string | undefined)?.trim() ?? 'default';
const _activeSkin = resolveActiveSkin(SKIN_ID);
if (!_activeSkin) {
  console.warn(`[state-machine] No skin found for VITE_SKIN_ID="${SKIN_ID}". customPages will be empty.`);
}
const skinCustomPages = _activeSkin?.customPages ?? [];

/**
 * Resolves the skin's configured board workflow and redirects to it. Split
 * out from HomeRedirect so useWorkflows() (an API call) only ever runs for a
 * skin that opts into homePath: 'pipeline' — every other skin's "/" render
 * never mounts this component at all.
 *
 * Matches on skin.board.machineName rather than just taking workflows[0] —
 * once an org has more than one active workflow (e.g. a second, unrelated
 * team's own workflow), "whichever the API returns first" is not
 * necessarily the one this skin is built around. Falls back to workflows[0]
 * only if the configured machine name isn't found, preserving today's
 * behavior for skins that don't set one.
 */
function PipelineHomeRedirect() {
  const { workflows, loading } = useWorkflows();
  const { skin } = useSkin();
  if (loading) return null;
  const configuredWorkflow = workflows.find((w) => w.slug === skin.board.machineName);
  const boardWorkflowId = (configuredWorkflow ?? workflows[0])?.id;
  return <Navigate to={boardWorkflowId ? `/pipeline/${boardWorkflowId}` : '/workflows'} replace />;
}

/**
 * Redirects "/" and unmatched routes to the skin's configured home surface.
 * Default skins (homePath unset) land on /workflows exactly as before, with
 * zero extra API calls — identical to the previous hardcoded <Navigate>. A
 * skin with homePath: 'pipeline' lands on its board instead, once the first
 * live workflow id is known. Any other string is an arbitrary skin-owned
 * path (typically a customPages route) the skin wants as its landing surface.
 */
function HomeRedirect() {
  const { skin } = useSkin();
  const target = resolveSkinHomePath(skin.homePath);
  if (target === 'pipeline') {
    return <PipelineHomeRedirect />;
  }
  return <Navigate to={target} replace />;
}

// Fallback for the outermost route Suspense boundary, which also covers
// pre-auth routes (login, OAuth callback, pending-approval, etc.) — those
// pages have nothing dashboard-shaped to mock up, so the generic
// SkeletonPage card-grid used inside the authenticated app briefly flashed
// a completely unrelated fake layout on top of them. A minimal, neutral
// spinner reads correctly on every route instead.
function RouteLoadingFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  );
}

/**
 * Full-screen layout for Agent Mode: authenticated + agent context, but WITHOUT
 * AppLayout chrome (no sidebar/topbar), so the page takes over the screen.
 */
function AgentModeLayout() {
  return (
    <ProtectedRoute>
      {/* GlobalEntityFilterProvider is normally mounted inside AppLayout; Agent
          Mode skips AppLayout but its canvas reuses real workflow components
          (PipelineBoardWidget → usePipelineBoardData → useWorkflowEntities)
          that consume this context, so it must be provided here too. */}
      <GlobalEntityFilterProvider>
        <AgentProvider>
          <Suspense fallback={<SkeletonPage />}>
            <Outlet />
          </Suspense>
        </AgentProvider>
      </GlobalEntityFilterProvider>
    </ProtectedRoute>
  );
}

/**
 * Route guard for surfaces an org has hidden via Settings → Display. The nav
 * filter (applyFlagFilters in App-Layout) only removed the link — typing the URL
 * still rendered the page.
 *
 * Only sound for flags that default to *shown*: `organization` (and so its
 * flags) resolves a tick after auth finishes, and during that window a
 * default-hidden flag (hideWhatsNew) would bounce orgs that opted in. Hence the
 * narrow union rather than `keyof FeatureFlags`.
 */
function FlagGate({ flag }: { flag: 'hideRecords' | 'hideDashboard' | 'hideAgent' }) {
  const flags = useFeatureFlags();
  return flags[flag] ? <Navigate to="/" replace /> : <Outlet />;
}

function ProtectedLayout() {
  return (
    <ProtectedRoute>
      <AgentProvider>
        <AppLayout>
          {/* Scoped to the routed content only — a Suspense boundary here
              (rather than one wrapping the whole <Routes> tree) keeps the
              sidebar/nav mounted across page transitions instead of
              flashing the entire shell to the fallback on every
              not-yet-visited lazy route. */}
          <Suspense fallback={<SkeletonPage />}>
            <Outlet />
          </Suspense>
        </AppLayout>
      </AgentProvider>
    </ProtectedRoute>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <OrgDocumentHead />
        <OrgSelectorProvider>
          <Suspense fallback={<RouteLoadingFallback />}>
          <Routes>
              <Route path="/" element={<HomeRedirect />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/forgot-password" element={<ForgotPasswordPage />} />
              <Route path="/reset-password" element={<ResetPasswordPage />} />
              <Route path="/pending-approval" element={<PendingApprovalPage />} />
              <Route path="/pending-org-approval" element={<PendingOrgApprovalPage />} />
              <Route path="/accept-invite" element={<AcceptInvitePage />} />
              <Route path="/auth/google/callback" element={<GoogleCallbackPage />} />
              <Route path="/auth/microsoft/callback" element={<MicrosoftCallbackPage />} />
              <Route path="/auth/remote-mcp/callback" element={<RemoteMcpCallbackPage />} />
              <Route path="/forms/submit/:token" element={<PublicFormPage />} />

              {/* Full-screen Agent Mode — authenticated but outside AppLayout chrome. */}
              <Route element={<AgentModeLayout />}>
                <Route element={<FlagGate flag="hideAgent" />}>
                  <Route path="/agent" element={<AgentModePage />} />
                </Route>
              </Route>

              <Route element={<ProtectedLayout />}>
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/workflows" element={<WorkflowsPage />} />
                <Route
                  path="/automations"
                  element={<Navigate to="/settings?tab=automations" replace />}
                />
                <Route element={<FlagGate flag="hideRecords" />}>
                  <Route path="/records" element={<RecordsPage />} />
                  <Route path="/records/:entityType" element={<RecordDetailPage />} />
                </Route>
                <Route path="/bulk-import" element={<BulkImportPage />} />
                <Route path="/pipeline/:id" element={<PipelinePage/>} />
                <Route path="/pipeline/:id/entity/:entityId" element={<EntityDetailPage />} />
                <Route path="/funnel/create" element={<FunnelEditorPage />} />
                <Route
                  path="/funnel/create/wizard"
                  element={<Navigate to="/funnel/create?view=wizard" replace />}
                />
                <Route path="/funnel/:stateMachineId/edit" element={<FunnelEditorPage />} />
                <Route
                  path="/integrations/google-calendar/callback"
                  element={<GoogleCalendarCallbackPage />}
                />
                <Route element={<FlagGate flag="hideDashboard" />}>
                  <Route path="/dashboard" element={<DashboardPage />} />
                </Route>
                <Route path="/changelogs" element={<ChangelogsPage />} />
                {skinCustomPages.map((page) => (
                  <Route
                    key={page.path}
                    path={page.path}
                    element={<page.component />}
                  />
                ))}
              </Route>

              <Route path="*" element={<HomeRedirect />} />
          </Routes>
          </Suspense>
        </OrgSelectorProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
