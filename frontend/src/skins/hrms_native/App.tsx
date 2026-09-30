import { BrandFooter, BrandLogo, PublicLayout } from './components/Brand';
import './brand.css';
import CockpitPage, { CockpitInbox } from './pages/CockpitPage';
import PublishedContent from './pages/PublishedContent';
import { lazy, Suspense, useEffect, useMemo, type ReactNode } from 'react';

import { Settings } from 'lucide-react';

import { BrowserRouter, Link, Navigate, NavLink, Outlet, Route, Routes } from 'react-router-dom';

import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';

import { AuthProvider, ProtectedRoute, useAuth } from '../../core/auth';

import { OrgSelectorProvider } from '../../core/contexts/OrgSelectorContext';

import { request } from '../../core/services/api/client';

import { useHrmsCapabilities } from './capabilities';

import EmployeeDirectoryPage from './pages/EmployeeDirectoryPage';

import OnboardingPage from './pages/OnboardingPage';

import LeaveRequestsPage from './pages/LeaveRequestsPage';

import WorkflowsPage from './pages/WorkflowsPage';

import PerformancePage from './pages/PerformancePage';
import ProjectsPage, { ProjectInbox } from './pages/ProjectsPage';
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

  const items = [

    { path: '/hrms/my-work', label: 'Quick actions' },

    ...(caps.data?.capabilities.includes('employee:read') ? [{ path: '/hrms/employees', label: 'Employees' }] : []),

    ...(caps.data?.capabilities.includes('onboarding:view') ? [{ path: '/hrms/onboarding', label: 'Onboarding' }] : []),

    { path: '/hrms/leave', label: 'Leave Requests' },

    { path: '/hrms/performance', label: 'Performance' },

    ...(caps.data?.capabilities.includes('project:view') ? [{ path: '/hrms/projects', label: 'Projects' }] : []),

    ...(caps.data?.capabilities.includes('cockpit:view') ? [{path:'/hrms/cockpit',label:'HR Cockpit'}] : []),
    {path:'/hrms/content',label:'Published information'},
    { path: '/hrms/workflows', label: 'Workflows' },

  ];

  return <div className="hrms-brand min-h-screen bg-slate-50 md:flex">

    <aside className="flex flex-col border-r bg-white p-5 md:sticky md:top-0 md:h-screen md:w-72 md:shrink-0">

      <Link to="/hrms/my-work" className="mb-8 flex items-center gap-3 text-lg font-semibold"><BrandLogo /></Link>

      <nav aria-label="Main navigation" className="flex min-h-0 flex-wrap gap-2 overflow-y-auto md:flex-col md:flex-nowrap">{items.map(item =>

        <NavLink key={item.path} to={item.path} className={({isActive}) => `rounded-full px-5 py-3 ${isActive ? 'bg-blue-700 text-white' : 'text-slate-600 hover:bg-slate-100'}`}>{item.label}</NavLink>)}</nav>

      {caps.data?.capabilities.includes('platform:configure') && <nav aria-label="Configuration navigation" className="mt-4 pt-3 md:mt-auto">
        <NavLink to="/settings" className={({isActive}) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium ${isActive ? 'bg-blue-100 text-blue-900' : 'text-slate-600 hover:bg-slate-100'}`}>
          <Settings size={18} aria-hidden="true" />Settings
        </NavLink>
      </nav>}

    </aside>

    <div className="flex min-h-screen min-w-0 flex-1 flex-col">

      <header className="flex items-center justify-end gap-4 border-b bg-white px-6 py-4"><div className="text-right"><p className="font-medium">{user?.fullName}</p><p className="text-sm text-slate-500">{caps.data?.roles.map(role => role.replace(/^hrms_/, '').replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase())).join(' · ') ?? 'Loading role…'}</p></div><button onClick={() => void logout()} className="rounded-lg border px-3 py-2">Sign out</button></header>

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



type WorkCase = { entity_id: string; employee_name: string; steps: { sequence: number; title: string; owner_name: string; can_complete: boolean; due_date: string | null }[] };

function MyWork() {
  const caps=useHrmsCapabilities();

  const query = useQuery({ queryKey: ['hrms', 'my-work'], queryFn: () => request<WorkCase[]>('/hrms/onboarding') });

  const actions = query.data?.flatMap(c => c.steps.filter(s => s.can_complete).map(s => ({...s, caseId: c.entity_id, employee: c.employee_name}))) ?? [];

  return <main className="mx-auto max-w-5xl space-y-5 p-6"><h1 className="text-2xl font-semibold">My Work</h1><p className="text-slate-600">Your assigned tasks and approvals.</p>

    <Link to="/hrms/leave" className="inline-block rounded-full border bg-white px-5 py-3">Open leave requests and approvals</Link>

    <Link to="/hrms/performance" className="ml-3 inline-block rounded-full border bg-white px-5 py-3">Open performance reviews and approvals</Link>

    {caps.data?.capabilities.includes('project:view') && <Link to="/hrms/projects" className="inline-block rounded-full border bg-white px-5 py-3">Open projects</Link>}
    <CockpitInbox />
    <ProjectInbox />

    {query.isLoading && <p>Loading actions…</p>}{query.isError && <p role="alert">Unable to load your actions.</p>}

    {!query.isLoading && !query.isError && actions.length === 0 && <p>No onboarding actions are ready for you.</p>}

    <ul className="space-y-3">{actions.map(a => <li key={`${a.caseId}-${a.sequence}`} className="rounded-xl border bg-white p-5"><p className="font-semibold">{a.employee} · {a.title}</p><p className="mt-1 text-sm text-slate-500">Owner: {a.owner_name}</p><Link className="mt-3 inline-block text-blue-700 underline" to={`/hrms/workflows?case=${a.caseId}`}>Open workflow and complete step</Link></li>)}</ul>

  </main>;

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

      <Route path="/hrms/my-work" element={<MyWork />} />

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

