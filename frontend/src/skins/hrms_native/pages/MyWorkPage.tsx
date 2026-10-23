import { EmployeeWorkflowActions } from '../workflows/EmployeeWorkflowActions';
import { useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, BriefcaseBusiness, CalendarCheck2, FileCheck2, Home, TrendingUp, UserRoundPlus, type LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';
import { request } from '@/core/services/api/client';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { useAuth } from '../../../core/auth';
import { useHrmsCapabilities } from '../capabilities';
import { PageHero } from '../components/PageHero';
import { Illustration } from '../components/Illustration';
import { Pager, Segmented } from '../components/ListKit';
import { usePaged } from '../components/useList';
import { usePrefersReducedMotion } from '../components/useReducedMotion';
import { formatDate, toDate, todayIso } from '../public-info/format';
import CockpitPage, { CONTENT_LABELS, CONTENT_TYPES } from './CockpitPage';
import { WfhDecision } from './WorkFromHome';
import type { LeaveItem } from './LeaveRequestsPage';
import { ComingUp } from '../workspace/ComingUp';
import { isForbidden, retryUnlessForbidden, useWaitingActions, type WaitingSource } from '../workspace/useWaitingActions';

type Area = WaitingSource['key'];
type Task = { key: string; area: Area; title: string; detail: string; feedback?: string | null; action: ReactNode };

const AREAS: Record<Area, { label: string; icon: LucideIcon; tab?: string }> = {
  offboarding: {label:'Employee offboarding',icon:UserRoundPlus},
  onboarding: {label:'Employee onboarding',icon:UserRoundPlus},
  users: { label: 'New users', icon: UserRoundPlus },
  leave: { label: 'Leave', icon: CalendarCheck2 },
  cockpit: { label: 'HR content', icon: FileCheck2 },
  projects: { label: 'Projects', icon: BriefcaseBusiness },
  wfh: { label: 'Work from home', icon: Home, tab: 'WFH' },
  performance: { label: 'Performance', icon: TrendingUp },
};

function greeting(hour: number) {
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

/** Due dates arrive as ISO timestamps; show the calendar day. */
const day = (iso: string | null | undefined) => { const d = toDate(iso?.slice(0, 10)); return d ? formatDate(d) : iso ?? ''; };
const humanize = (value: string) => value.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase());
const joined = (...parts: unknown[]) => parts.filter(p => typeof p === 'string' && p.trim()).join(' · ');
type PerformanceTask = { kind: string; data: Record<string, unknown>; cycle_name?: string; employee_name?: string; due_date?: string | null };
const performanceTitle = (item: PerformanceTask) => {
  const person = String(item.data.employee_name || item.employee_name || '');
  return item.kind === 'HRMS.PerformanceCycle' ? String(item.data.name ?? 'Performance cycle')
    : item.kind === 'HRMS.ProjectFeedback' ? `Feedback for ${person || 'a colleague'}`
      : person ? `${person} · review` : 'Performance review';
};

function Go({ to, children }: { to: string; children: ReactNode }) {
  return <Link className="hrms-lk-link" to={to}>{children}<ArrowRight size={13} aria-hidden="true" /></Link>;
}

/**
 * My Tasks: one prioritized list of everything waiting on the signed-in person, filterable by area,
 * with the one action each item needs. Uses the same sources as the sidebar badge and the bell.
 */
export default function MyWorkPage() {
  const { user } = useAuth();
  const caps = useHrmsCapabilities();
  const onboardingOnly = caps.data?.roles.includes('hrms_onboarding_employee') ?? false;
  const motion = !usePrefersReducedMotion();
  const waiting = useWaitingActions();
  const [area, setArea] = useState<string>('all');
  const [reviewing, setReviewing] = useState<string | null>(null);

  const myLeave = useQuery({ queryKey: ['hrms', 'leave', 'mine'], queryFn: () => request<LeaveItem[]>('/hrms/leave-requests?view=mine&limit=100'), retry: retryUnlessForbidden,
    enabled: caps.isFetched && caps.data?.employee_profile !== false });
  const leaveUnavailable = caps.data?.employee_profile === false || isForbidden(myLeave.error);
  const today = todayIso();
  const nextLeave = myLeave.data?.filter(item => (item.end_date || item.start_date) >= today && !['rejected', 'cancelled'].includes(item.state))
    .sort((a, b) => a.start_date.localeCompare(b.start_date))[0];

  const tasks: Task[] = [
    ...(waiting.myOffboarding.data??[]).filter(item=>item.actions.length>0).map(item=>({key:`my-exit-${item.entity_id}`,area:'offboarding' as const,title:'Your employee handover',detail:item.state,action:<Go to={`/hrms/my-offboarding/${item.entity_id}`}>Complete form</Go>})),
    ...waiting.employeeWork.filter(item=>item.actions.length>0).map(item=>({key:`e-${item.entity_id}-${item.workflow_id}`,area:'onboarding' as const,title:item.title,feedback:item.verifier_feedback,
      detail:joined(item.workflow_label,item.current_state,item.feedback_status==='resolved'?'Previous feedback resolved by HR':item.feedback_status==='submitted'?'Corrections submitted, awaiting HR review':'',item.due_date?`Due ${day(item.due_date)}`:''),action:<EmployeeWorkflowActions key={item.current_state} item={item}/>})),
    ...(waiting.offboarding.data??[]).map(item=>({key:`exit-${item.entity_id}`,area:'offboarding' as const,title:item.summary_fields.identifier||'Employee exit',detail:item.current_state,action:<Go to={`/hrms/workflows?workflow=${encodeURIComponent(item.machine_name)}&case=${item.entity_id}`}>Open</Go>})),
    ...(waiting.userApprovals.data ?? []).map(person => ({ key: `u-${person.id}`, area: 'users' as const, title: person.full_name, detail: joined('New account', person.email),
      action: <Go to="/settings?tab=users">Review</Go> })),
    ...waiting.pendingLeave.map(item => ({ key: `l-${item.entity_id}`, area: 'leave' as const, title: item.employee_name,
      detail: joined(item.leave_type, item.end_date && item.end_date !== item.start_date ? `${day(item.start_date)} – ${day(item.end_date)}` : day(item.start_date), item.reason),
      action: <Go to="/hrms/leave">Review</Go> })),
    ...waiting.cockpitActions.map(item => ({ key: `c-${item.entity_id}`, area: 'cockpit' as const, title: String(item.data.title ?? 'HR content'),
      detail: joined(CONTENT_LABELS[CONTENT_TYPES.indexOf(item.kind)], item.state_label, item.data.author_name ? `by ${item.data.author_name}` : ''),
      action: <button type="button" className="hrms-lk-link" onClick={() => setReviewing(item.entity_id)}>{item.actions.includes('approve') ? 'Review' : 'Publish'}<ArrowRight size={13} aria-hidden="true" /></button> })),
    ...waiting.projectActions.map(item => ({ key: `p-${item.id}`, area: 'projects' as const, title: item.project_name,
      detail: joined(item.kind === 'HRMS.ProjectChange' ? 'Project change' : 'Allocation request', item.data.requested_by_name ? `Requested by ${item.data.requested_by_name}` : ''),
      action: <Go to={`/hrms/workflows?case=${item.id}`}>Review</Go> })),
    ...waiting.wfhRequests.map(item => ({ key: `w-${item.entity_id}`, area: 'wfh' as const, title: item.employee_name, detail: joined(item.dates.map(d => day(d)).join(', '), item.reason),
      action: <WfhDecision item={item} /> })),
    ...waiting.performanceActions.map(item => ({ key: `pf-${item.id}`, area: 'performance' as const, title: performanceTitle(item),
      detail: joined(item.kind === 'HRMS.PerformanceCycle' ? 'Review cycle' : item.cycle_name, `Next: ${item.actions.filter(a => a !== 'reassign').map(humanize).join(', ')}`, item.due_date ? `Due ${day(item.due_date)}` : ''),
      action: <Go to="/hrms/performance">Open</Go> })),
  ];

  // Every area this person can act on gets a tab, so all work types are visible even when empty.
  const areas = waiting.sources;
  const current = area === 'all' || areas.some(s => s.key === area) ? area : 'all';
  const visible = current === 'all' ? tasks : tasks.filter(t => t.area === current);
  const paged = usePaged(visible, 10, current);
  const failed = waiting.sources.filter(s => s.error);
  const firstName = user?.fullName?.trim().split(/\s+/)[0] || 'there';
  const dateLine = new Intl.DateTimeFormat(undefined, { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date());
  const nextLeaveDate = nextLeave ? toDate(nextLeave.start_date) : null;

  return <main className={`hrms-ws-page hrms-mywork${motion ? ' hrms-ws--motion' : ''}`}>
    <PageHero title={`${greeting(new Date().getHours())}, ${firstName}`} illustration="my-work"
      intro={`${dateLine} · ${waiting.loading ? 'Checking what needs you…' : waiting.total ? `${waiting.total} ${waiting.total === 1 ? 'item needs' : 'items need'} your attention.` : 'You’re all caught up.'}`}
      actions={leaveUnavailable ? undefined : <Link className="hrms-primary-button" to="/hrms/leave">Request leave</Link>}
      stats={[
        { label: 'Waiting on you', value: waiting.loading ? '…' : waiting.total, tone: waiting.total ? 'attention' : 'positive' },
        { label: 'Next time off', value: leaveUnavailable ? '—' : myLeave.isLoading || !caps.isFetched ? '…' : nextLeaveDate ? <span title={`${nextLeave?.leave_type} · ${nextLeave?.state}`}>{formatDate(nextLeaveDate)}</span> : 'None planned' },
      ]} />

    <div className="hrms-mw-layout">
      <section className="hrms-lk-card hrms-mw-tasks" aria-labelledby="hrms-tasks-title">
        <div className="hrms-lk-card-head">
          <h2 id="hrms-tasks-title">Tasks &amp; approvals</h2>
          {!onboardingOnly && <Link className="hrms-coming-all" to="/hrms/workflows">All workflows<ArrowRight size={14} aria-hidden="true" /></Link>}
        </div>
        {areas.length > 1 && <div className="hrms-mw-areas"><Segmented label="Filter by area" value={current} onChange={setArea}
          segments={[{ id: 'all', label: 'All', count: tasks.length }, ...areas.map(s => ({ id: s.key, label: AREAS[s.key].tab ?? AREAS[s.key].label, count: s.loading && !s.error ? undefined : s.count }))]} /></div>}
        {failed.length > 0 && <div role="alert" className="hrms-task-alert">Couldn’t load {failed.map(s => AREAS[s.key].label).join(', ')}.<button type="button" onClick={() => failed.forEach(s => s.retry())}>Try again</button></div>}
        {visible.length > 0 ? <ul className="hrms-task-list">{paged.items.map(task => {
          const Icon = AREAS[task.area].icon;
          return <li key={task.key} className="hrms-task">
            <span className="hrms-task-icon" title={AREAS[task.area].label}><Icon size={16} aria-hidden="true" /></span>
            <div className="hrms-task-main">
              <strong>{task.title}</strong>
              <small>{current === 'all' && <span className="hrms-task-area">{AREAS[task.area].label}</span>}{task.detail}</small>
              {task.feedback && <div className="mt-3 rounded-xl border border-blue-200 bg-blue-50 p-3"><strong>Verifier feedback</strong><p className="whitespace-pre-wrap break-words mt-1">{task.feedback}</p></div>}
            </div>
            <div className="hrms-task-action">{task.action}</div>
          </li>;
        })}</ul> : waiting.loading ? <ul className="hrms-task-list" aria-busy="true" aria-label="Loading tasks">{[0, 1, 2].map(i => <li key={i} className="hrms-task hrms-task--skeleton" />)}</ul>
          : <div className="hrms-task-empty"><Illustration name="all-clear" animate={motion} className="hrms-task-empty-art" /><h3>{current === 'all' ? 'You’re all caught up' : `Nothing waiting in ${AREAS[current as Area].label}`}</h3><p>{current === 'all' ? 'New approvals and tasks for your role will appear here.' : 'New items will appear here as soon as they need you.'}</p></div>}
        <Pager paged={paged} noun={current === 'all' ? 'tasks' : AREAS[current as Area].label.toLowerCase()} />
      </section>
      {(waiting.myOffboarding.data??[]).map(item=><section key={item.entity_id} className="hrms-lk-card p-6"><h2 className="font-semibold">Your offboarding</h2><p className="my-3">{item.state}</p><Go to={`/hrms/my-offboarding/${item.entity_id}`}>View progress</Go></section>)}
      {waiting.myOffboarding.isError&&<p role="alert">Unable to load your offboarding status. <button onClick={()=>void waiting.myOffboarding.refetch()}>Retry</button></p>}
      {waiting.employeeWork.filter(item=>item.is_own_onboarding).map(item=><section key={`status-${item.entity_id}-${item.workflow_id}`} className="hrms-lk-card p-6" aria-label="Your onboarding status">
        <h2 className="font-semibold">Your onboarding</h2>
        <p className="mt-2">{item.current_state}</p>
        <p className="mt-2 text-sm">{item.actions.length ? 'Your next action is listed in Tasks & approvals above.' : 'No action is needed from you at this step. Your status updates here as onboarding progresses.'}</p>
      </section>)}
      {!onboardingOnly && <ComingUp />}
    </div>

    <Sheet open={reviewing !== null} onOpenChange={open => { if (!open) setReviewing(null); }}>
      <SheetContent className="hrms-brand hrms-review-drawer overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-4xl">
        <SheetHeader><SheetTitle>Review HR content</SheetTitle></SheetHeader>
        {reviewing && <CockpitPage key={reviewing} entityId={reviewing} />}
      </SheetContent>
    </Sheet>
  </main>;
}
