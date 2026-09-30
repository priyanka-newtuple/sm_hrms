import { BrandFooter, PublicLayout } from './components/Brand';
import TenantHeader from './components/TenantHeader';
import './brand.css';
import CockpitPage from './pages/CockpitPage';
import PublishedContent from './pages/PublishedContent';
import { lazy, Suspense, useEffect, useMemo, type ReactNode } from 'react';

import { Settings, Zap, Users, UserRoundPlus, CalendarDays, TrendingUp, BriefcaseBusiness, SlidersHorizontal, Workflow } from 'lucide-react';

import { BrowserRouter, Navigate, NavLink, Outlet, Route, Routes } from 'react-router-dom';

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

  const { user, logout } = useAuth();

  const caps = useHrmsCapabilities();

  const allowed = (capability: string) => caps.data?.capabilities.includes(capability) ?? false;
  const groups = [
    { label: 'My work', items: [
      { path: '/hrms/my-work', label: 'My work', icon: Zap },
      { path: '/hrms/leave', label: 'Leave requests', icon: CalendarDays },
      { path: '/hrms/performance', label: 'Performance', icon: TrendingUp },
    ] },
    { label: 'People', items: [
      ...(allowed('employee:read') ? [{ path: '/hrms/employees', label: 'Employees', icon: Users }] : []),
      ...(allowed('onboarding:view') ? [{ path: '/hrms/onboarding', label: 'Onboarding', icon: UserRoundPlus }] : []),
    ] },
    { label: 'Delivery', items: allowed('project:view') ? [{ path: '/hrms/projects', label: 'Projects', icon: BriefcaseBusiness }] : [] },
    { label: 'HR publishing', items: allowed('cockpit:view') ? [{ path: '/hrms/cockpit', label: 'HR Cockpit', icon: SlidersHorizontal }] : [] },
    { label: 'Tracking', items: [{ path: '/hrms/workflows', label: 'Workflows', icon: Workflow }] },
  ].filter(group => group.items.length);

  return <div className="hrms-brand min-h-screen bg-slate-50 md:flex">

    <aside className="flex flex-col border-r bg-white p-5 md:sticky md:top-0 md:h-screen md:w-72 md:shrink-0">

      <TenantHeader />

      <nav aria-label="Main navigation" className="hrms-grouped-navigation">
        {groups.map(group => <section key={group.label} className="hrms-nav-group" aria-label={group.label}>
          <h2>{group.label}</h2>
          {group.items.map(item => <NavLink key={item.path} to={item.path} className={({isActive}) => `hrms-nav-link rounded-full px-5 py-3 ${isActive ? 'bg-blue-700 text-white' : 'text-slate-600 hover:bg-slate-100'}`}><item.icon size={19} strokeWidth={1.25} aria-hidden="true"/><span>{item.label}</span></NavLink>)}
        </section>)}
        {caps.isLoading && <p className="hrms-nav-feedback" role="status">Loading work areas…</p>}
        {caps.isError && <div className="hrms-nav-feedback" role="alert"><p>Some work areas could not be loaded.</p><button onClick={()=>void caps.refetch()}>Retry permissions</button></div>}
      </nav>

      {caps.data?.capabilities.includes('platform:configure') && <nav aria-label="Configuration navigation" className="mt-4 pt-3 md:mt-auto">
        <NavLink to="/settings" className={({isActive}) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium ${isActive ? 'bg-blue-100 text-blue-900' : 'text-slate-600 hover:bg-slate-100'}`}>
          <Settings size={19} strokeWidth={1.25} aria-hidden="true" />Settings
        </NavLink>
      </nav>}

    </aside>

    <div className="flex min-h-screen min-w-0 flex-1 flex-col">

      <header className="flex items-center justify-end gap-4 border-b bg-white px-6 py-4"><div className="text-right"><p className="font-medium">{user?.fullName}</p><p className="text-sm text-slate-500">{caps.data?.roles.map(role => role.replace(/^hrms_/, '').replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase())).join(' · ') ?? (caps.isPending ? 'Loading role…' : 'Role unavailable — retry permissions')}</p></div><button onClick={() => void logout()} className="rounded-lg border px-3 py-2">Sign out</button></header>

      <div className="min-w-0 flex-1"><Outlet /></div>
      <BrandFooter compact />

    </div>

  </div>;

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

      <Route path="/hrms/workflows" element={<WorkflowsPage />} />

      <Route path="/workflows" element={<Navigate to="/hrms/workflows" replace />} />

      <Route path="/pipeline/:id/*" element={<Navigate to="/hrms/workflows" replace />} />

      <Route path="*" element={<Navigate to="/hrms/my-work" replace />} />

    </Route>

  </Routes></Suspense></OrgSelectorProvider></SessionQueries></AuthProvider></BrowserRouter>;

}

