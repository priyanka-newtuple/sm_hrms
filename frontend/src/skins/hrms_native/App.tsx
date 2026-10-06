import { PublicLayout } from './components/Brand';
import './brand.css';
import './workspace/workspace.css';
import CockpitPage from './pages/CockpitPage';
import PublishedContent from './pages/PublishedContent';
import { lazy, Suspense, useEffect, useMemo, type ReactNode } from 'react';

import { WorkspaceShell } from './workspace/Shell';

import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { AuthProvider, ProtectedRoute, useAuth } from '../../core/auth';

import { OrgSelectorProvider } from '../../core/contexts/OrgSelectorContext';

import MyWorkPage from './pages/MyWorkPage';

import { useHrmsCapabilities } from './capabilities';

import EmployeeDirectoryPage from './pages/EmployeeDirectoryPage';

import OnboardingPage from './pages/OnboardingPage';

import LeaveRequestsPage from './pages/LeaveRequestsPage';

import WorkflowsPage from './pages/WorkflowsPage';

import PerformancePage from './pages/PerformancePage';
import ProjectsPage from './pages/ProjectsPage';
import AllocationsPage from './pages/AllocationsPage';
import { ConfigurationGuard } from './pages/PlatformSettings';
const PlatformSettings = lazy(() => import('./pages/PlatformSettings'));
const FunnelEditor = lazy(() => import('../../pages/funnel'));



const LoginPage = lazy(() => import('./pages/BrandedLoginPage'));

const ForgotPasswordPage = lazy(() => import('../../pages/auth/Forgot-Password'));

const ResetPasswordPage = lazy(() => import('../../pages/auth/Reset-Password'));

const GoogleCallbackPage = lazy(() => import('../../pages/auth/GoogleCallbackPage'));

const MicrosoftCallbackPage = lazy(() => import('../../pages/auth/MicrosoftCallbackPage'));

const AcceptInvitePage = lazy(() => import('../../pages/auth/AcceptInvitePage'));

const PendingApprovalPage = lazy(() => import('../../pages/auth/PendingApprovalPage'));



function SessionQueries({ children }: { children: ReactNode }) {

  const { user } = useAuth();

  // A different signed-in person must never see the previous person's cached HR data.

  const client = useMemo(() => new QueryClient({ defaultOptions: {

    queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: true },

  } }), [user?.id, user?.organizationId]);

  useEffect(() => () => { void client.cancelQueries(); client.clear(); }, [client]);

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;

}



function Layout() {
  return <WorkspaceShell />;
}



function OnboardingManagement() {

  const caps = useHrmsCapabilities();

  if (caps.isLoading) return <p className="p-6">Loading permissions…</p>;

  if (!caps.data?.capabilities.includes('onboarding:view')) return <Navigate to="/hrms/my-work" replace />;

  return <OnboardingPage />;

}



export default function App() {

  return <BrowserRouter><AuthProvider><SessionQueries><OrgSelectorProvider><Suspense fallback={<p className="p-8" role="status">Loading…</p>}><Routes>

    <Route element={<PublicLayout />}>
    <Route path="/login" element={<LoginPage />} />
    <Route path="/public" element={<PublishedContent publicPage />} />

    <Route path="/forgot-password" element={<ForgotPasswordPage />} />

    <Route path="/reset-password" element={<ResetPasswordPage />} />

    <Route path="/pending-approval" element={<PendingApprovalPage />} />

    <Route path="/accept-invite" element={<AcceptInvitePage />} />

    <Route path="/auth/google/callback" element={<GoogleCallbackPage />} />

    <Route path="/auth/microsoft/callback" element={<MicrosoftCallbackPage />} />

    </Route>
    <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>

      <Route path="/settings" element={<PlatformSettings />} />
      <Route path="/funnel/create" element={<ConfigurationGuard><FunnelEditor /></ConfigurationGuard>} />
      <Route path="/funnel/:stateMachineId/edit" element={<ConfigurationGuard><FunnelEditor /></ConfigurationGuard>} />
      <Route path="/funnel/create/wizard" element={<Navigate to="/funnel/create?view=wizard" replace />} />
      <Route path="/hrms/employees" element={<EmployeeDirectoryPage />} />

      <Route path="/hrms/onboarding" element={<OnboardingManagement />} />

      <Route path="/hrms/leave" element={<LeaveRequestsPage />} />

      <Route path="/hrms/performance" element={<PerformancePage />} />

      <Route path="/hrms/my-work" element={<MyWorkPage />} />

      <Route path="/hrms/cockpit" element={<CockpitPage />} />
      <Route path="/hrms/content" element={<PublishedContent />} />
      <Route path="/hrms/projects" element={<ProjectsPage />} />
      <Route path="/hrms/allocations" element={<AllocationsPage />} />

      <Route path="/hrms/workflows" element={<WorkflowsPage />} />

      <Route path="/workflows" element={<Navigate to="/hrms/workflows" replace />} />

      <Route path="/pipeline/:id/*" element={<Navigate to="/hrms/workflows" replace />} />

      <Route path="*" element={<Navigate to="/hrms/my-work" replace />} />

    </Route>

  </Routes></Suspense></OrgSelectorProvider></SessionQueries></AuthProvider></BrowserRouter>;

}

