import { useQuery } from '@tanstack/react-query';
import { request } from '@/core/services/api/client';
import { useHrmsCapabilities } from '../capabilities';
import { useCockpitBoard } from '../pages/CockpitPage';
import { usePerformance } from '../pages/PerformancePage';
import { awaitingYou } from '../pages/performanceAwaiting';
import { useProjects } from '../pages/ProjectsPage';
import type { LeaveItem } from '../pages/LeaveRequestsPage';
import { useWfhInbox } from '../pages/WorkFromHome';

export type OnboardingCase = { entity_id: string; employee_name: string; steps: { sequence: number; title: string; owner_name: string; can_complete: boolean; assigned_to_me?: boolean; due_date: string | null }[] };

// Accounts without a linked employee profile (e.g. bootstrap administrators) get 403 from leave APIs.
export const isForbidden = (error: unknown) => (error as { status?: number } | null)?.status === 403;
export const retryUnlessForbidden = (count: number, error: unknown) => !isForbidden(error) && count < 1;

export interface WaitingSource { key: 'users' | 'leave' | 'cockpit' | 'projects' | 'onboarding' | 'wfh' | 'performance'; label: string; path: string; count: number; loading: boolean }

/**
 * What the signed-in person can act on right now, per work area. Shares query keys with the pages,
 * so the sidebar badges, the notification bell and My Work always show the same numbers.
 * Only areas the person can see are returned.
 */
export function useWaitingActions() {
  const caps = useHrmsCapabilities();
  const has = (capability: string) => caps.data?.capabilities.includes(capability) ?? false;
  const onboarding = useQuery({ queryKey: ['hrms', 'my-work'], queryFn: () => request<OnboardingCase[]>('/hrms/onboarding') });
  // Only pending approvals, so older history can never push waiting requests past the page limit.
  const leaveApprovals = useQuery({ queryKey: ['hrms', 'leave', 'approvals', 'pending'], queryFn: () => request<LeaveItem[]>('/hrms/leave-requests?view=approvals&state=pending&limit=200'), retry: retryUnlessForbidden,
    enabled: caps.isFetched && caps.data?.employee_profile !== false });
  const cockpit = useCockpitBoard();
  const projects = useProjects();
  const wfh = useWfhInbox();
  const performance = usePerformance();
  const isSuperAdmin = caps.data?.roles.includes('superadmin') ?? false;
  const userApprovals = useQuery({
    queryKey: ['hrms', 'user-approvals'],
    queryFn: () => request<{id: string; full_name: string; email: string}[]>('/hrms/user-approvals'),
    enabled: isSuperAdmin, retry: retryUnlessForbidden,
  });

  // HR may complete anyone's step from Onboarding; only steps assigned to you are waiting on you.
  const onboardingActions = onboarding.data?.flatMap(c => c.steps.filter(s => s.can_complete && (s.assigned_to_me ?? true)).map(s => ({ ...s, caseId: c.entity_id, employee: c.employee_name }))) ?? [];
  const pendingLeave = leaveApprovals.data?.filter(item => item.state === 'pending') ?? [];
  // Same rule as the Performance page's "Awaiting you".
  const performanceActions = performance.data ? awaitingYou(performance.data) : [];
  const cockpitActions = cockpit.data?.items.filter(item => item.actions.includes('approve') || item.actions.includes('publish')) ?? [];
  const projectActions = projects.data?.requests.filter(r => r.state === 'pending' && r.actions.includes('approve')) ?? [];

  const sources: WaitingSource[] = [
    { key: 'users' as const, label: 'New user approvals', path: '/settings?tab=users', count: userApprovals.data?.length ?? 0, loading: userApprovals.isLoading || userApprovals.isError, show: isSuperAdmin },
    { key: 'wfh' as const, label: 'WFH approvals', path: '/hrms/cockpit?area=wfh', count: wfh.data?.length ?? 0, loading: wfh.isLoading, show: has('wfh:approve') },
    { key: 'leave' as const, label: 'Leave approvals', path: '/hrms/leave', count: pendingLeave.length, loading: leaveApprovals.isLoading, show: (leaveApprovals.data?.length ?? 0) > 0 },
    { key: 'cockpit' as const, label: 'HR content', path: '/hrms/cockpit', count: cockpitActions.length, loading: cockpit.isLoading, show: has('cockpit:view') },
    { key: 'projects' as const, label: 'Projects', path: '/hrms/projects', count: projectActions.length, loading: projects.isLoading, show: has('project:view') },
    { key: 'performance' as const, label: 'Performance', path: '/hrms/performance', count: performanceActions.length, loading: performance.isLoading, show: performance.isSuccess },
    { key: 'onboarding' as const, label: 'Onboarding', path: has('onboarding:view') ? '/hrms/cockpit?area=onboarding' : '/hrms/my-work', count: onboardingActions.length, loading: onboarding.isLoading, show: true },
  ].flatMap(({ show, ...source }) => (show ? [source] : []));

  return {
    sources,
    total: sources.reduce((sum, source) => sum + source.count, 0),
    loading: caps.isLoading || sources.some(source => source.loading),
    countFor: (key: WaitingSource['key']) => sources.find(source => source.key === key)?.count ?? 0,
    userApprovals, isSuperAdmin, onboarding, onboardingActions, leaveApprovals, pendingLeave, performance, performanceActions,
  };
}
