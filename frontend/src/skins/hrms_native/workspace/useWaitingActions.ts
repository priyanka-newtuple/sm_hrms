import type { MyExit } from '../pages/MyOffboardingPage';
import { useQuery } from '@tanstack/react-query';
import { request } from '@/core/services/api/client';
import { useHrmsCapabilities } from '../capabilities';
import { useCockpitBoard } from '../pages/CockpitPage';
import { usePerformance } from '../pages/PerformancePage';
import { awaitingYou } from '../pages/performanceAwaiting';
import { useProjects } from '../pages/ProjectsPage';
import type { LeaveItem } from '../pages/LeaveRequestsPage';
import { useWfhInbox } from '../pages/WorkFromHome';


// Accounts without a linked employee profile (e.g. bootstrap administrators) get 403 from leave APIs.
export const isForbidden = (error: unknown) => (error as { status?: number } | null)?.status === 403;
export const retryUnlessForbidden = (count: number, error: unknown) => !isForbidden(error) && count < 1;

export interface WaitingSource { key: 'offboarding' | 'onboarding' | 'users' | 'leave' | 'cockpit' | 'projects' | 'wfh' | 'performance'; label: string; path: string; count: number; loading: boolean; error: boolean; retry: () => void }

/**
 * What the signed-in person can act on right now, per work area. Shares query keys with the pages,
 * so the sidebar badges, the notification bell and My Work always show the same numbers.
 * Only areas the person can see are returned.
 */
export function useWaitingActions() {
  const caps = useHrmsCapabilities();
  const has = (capability: string) => caps.data?.capabilities.includes(capability) ?? false;
  // Only pending approvals, so older history can never push waiting requests past the page limit.
  const leaveApprovals = useQuery({ queryKey: ['hrms', 'leave', 'approvals', 'pending'], queryFn: () => request<LeaveItem[]>('/hrms/leave-requests?view=approvals&state=pending&limit=200'), retry: retryUnlessForbidden,
    enabled: caps.isFetched && caps.data?.employee_profile !== false });
  const employeeWork = useQuery({queryKey:['hrms','employee-work'], queryFn:()=>request<EmployeeWork[]>('/hrms/employee-work'), retry:retryUnlessForbidden,refetchInterval:30_000});
  const myOffboarding=useQuery({queryKey:['hrms','my-offboarding'],queryFn:()=>request<MyExit[]>('/hrms/my-offboarding'),enabled:caps.isFetched,retry:retryUnlessForbidden,refetchInterval:30_000});
  const offboarding = useQuery({queryKey:['hrms','offboarding-inbox'],queryFn:()=>request<{entity_id:string;machine_name:string;current_state:string;summary_fields:Record<string,string>}[]>('/hrms/offboarding/inbox'),enabled:has('employee:exit'),retry:retryUnlessForbidden});
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

  const pendingLeave = leaveApprovals.data?.filter(item => item.state === 'pending') ?? [];
  // Same rule as the Performance page's "Awaiting you".
  const performanceActions = performance.data ? awaitingYou(performance.data) : [];
  const cockpitActions = cockpit.data?.items.filter(item => item.actions.includes('approve') || item.actions.includes('publish')) ?? [];
  const projectActions = projects.data?.requests.filter(r => r.state === 'pending' && r.actions.includes('approve')) ?? [];

  const sources: WaitingSource[] = [
    {key:'offboarding' as const,label:'Employee offboarding',path:'/hrms/my-work',count:(offboarding.data?.length??0)+(myOffboarding.data?.filter(r=>r.actions.length>0).length??0),loading:offboarding.isLoading||myOffboarding.isLoading,error:offboarding.isError||myOffboarding.isError,retry:()=>{void offboarding.refetch();void myOffboarding.refetch();},show:has('employee:exit')||(myOffboarding.data?.length??0)>0},
    {key:'onboarding' as const,label:'Employee onboarding',path:'/hrms/my-work',count:employeeWork.data?.filter(item=>item.actions.length>0).length??0,loading:employeeWork.isLoading,error:employeeWork.isError,retry:()=>void employeeWork.refetch(),show:!isForbidden(employeeWork.error)},
    { key: 'users' as const, label: 'New user approvals', path: '/settings?tab=users', count: userApprovals.data?.length ?? 0, loading: userApprovals.isLoading || userApprovals.isError, error: userApprovals.isError, retry: () => void userApprovals.refetch(), show: isSuperAdmin },
    { key: 'wfh' as const, label: 'WFH approvals', path: '/hrms/my-work', count: wfh.data?.length ?? 0, loading: wfh.isLoading, error: wfh.isError, retry: () => void wfh.refetch(), show: has('wfh:approve') },
    { key: 'leave' as const, label: 'Leave approvals', path: '/hrms/leave', count: pendingLeave.length, loading: leaveApprovals.isLoading, error: leaveApprovals.isError && !isForbidden(leaveApprovals.error), retry: () => void leaveApprovals.refetch(), show: caps.data?.employee_profile === true && !isForbidden(leaveApprovals.error) },
    { key: 'cockpit' as const, label: 'HR content', path: '/hrms/cockpit', count: cockpitActions.length, loading: cockpit.isLoading, error: cockpit.isError, retry: () => void cockpit.refetch(), show: has('cockpit:view') },
    { key: 'projects' as const, label: 'Projects', path: '/hrms/projects', count: projectActions.length, loading: projects.isLoading, error: projects.isError, retry: () => void projects.refetch(), show: has('project:view') },
    { key: 'performance' as const, label: 'Performance', path: '/hrms/performance', count: performanceActions.length, loading: performance.isLoading, error: false, retry: () => void performance.refetch(), show: performance.isSuccess },
  ].flatMap(({ show, ...source }) => (show ? [source] : []));

  return {
    sources, offboarding, myOffboarding, employeeWork: employeeWork.data??[],
    total: sources.reduce((sum, source) => sum + source.count, 0),
    loading: caps.isLoading || sources.some(source => source.loading),
    countFor: (key: WaitingSource['key']) => sources.find(source => source.key === key)?.count ?? 0,
    userApprovals, isSuperAdmin, leaveApprovals, pendingLeave, performance, performanceActions,
    cockpitActions, projectActions, wfhRequests: wfh.data ?? [],
  };
}

export type EmployeeWork = {feedback_status?:'requested'|'submitted'|'resolved'|null;is_own_onboarding?:boolean;verifier_feedback?:string|null;entity_id:string;workflow_id:string;title:string;workflow_label:string;current_state:string;due_date:string|null;actions:{trigger:string;label?:string;to_state:string;required_fields?:{field:string;required:boolean}[]}[]};
