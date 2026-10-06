import { useQuery } from '@tanstack/react-query';
import { ArrowRight, CalendarCheck2, CheckCircle2, UserRoundPlus } from 'lucide-react';
import { Link } from 'react-router-dom';
import { request, getApiErrorMessage } from '@/core/services/api/client';
import { useAuth } from '../../../core/auth';
import { useHrmsCapabilities } from '../capabilities';
import { WorkPanel } from '../components/WorkPanel';
import { AnimIcon, ArrowRightIcon, BookTextIcon, BriefcaseBusinessIcon, CalendarDaysIcon, TrendingUpIcon, type AnimatedIcon } from '../animated-icons';
import { LocalTime } from '../login/LocalTime';
import { ShinyText } from '../login/reactbits';
import { usePrefersReducedMotion } from '../components/useReducedMotion';
import { formatDate, toDate, todayIso } from '../public-info/format';
import { CockpitInbox } from './CockpitPage';
import { ProjectInbox } from './ProjectsPage';
import type { LeaveItem } from './LeaveRequestsPage';
import { Illustration } from '../components/Illustration';
import { ActionDonut } from '../workspace/ActionDonut';
import { ComingUp } from '../workspace/ComingUp';
import { isForbidden, retryUnlessForbidden, useWaitingActions } from '../workspace/useWaitingActions';
import '../login/login.css';

const roleName = (role: string) => role === 'superadmin' ? 'Super Admin' : role.replace(/^hrms_/, '').replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());

function greeting(hour: number) {
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

/** Direct-report leave requests waiting for this user's decision (same API as the Leave page). */
function LeaveInbox({ items, loading, error, retry }: { items: LeaveItem[]; loading: boolean; error?: string; retry: () => void }) {
  return <WorkPanel title="Leave approvals" description="Requests from your direct reports." icon={CalendarCheck2} count={items.length} loading={loading} error={error} retry={retry} empty="No leave requests are waiting for your decision.">
    <ul>{items.map(item => {
      const start = toDate(item.start_date), end = toDate(item.end_date);
      return <li className="hrms-work-item" key={item.entity_id}>
        <p className="hrms-work-item-context">{item.leave_type}</p>
        <h3>{item.employee_name}</h3>
        <p>{start ? formatDate(start) : item.start_date}{end && item.end_date !== item.start_date ? ` – ${formatDate(end)}` : ''}{item.reason ? ` · ${item.reason}` : ''}</p>
        <Link className="hrms-outline-button" to="/hrms/leave">Review request <ArrowRight size={15} aria-hidden="true" /></Link>
      </li>;
    })}</ul>
  </WorkPanel>;
}

export default function MyWorkPage() {
  const { user } = useAuth();
  const caps = useHrmsCapabilities();
  const motion = !usePrefersReducedMotion();
  const has = (capability: string) => caps.data?.capabilities.includes(capability) ?? false;
  const waiting = useWaitingActions();
  const { sources, total, onboarding, onboardingActions, leaveApprovals, pendingLeave } = waiting;
  const summaryLoading = waiting.loading;
  const myLeave = useQuery({ queryKey: ['hrms', 'leave', 'mine'], queryFn: () => request<LeaveItem[]>('/hrms/leave-requests?view=mine&limit=100'), retry: retryUnlessForbidden });
  const leaveUnavailable = isForbidden(myLeave.error);

  const today = todayIso();
  const nextLeave = myLeave.data?.filter(item => (item.end_date || item.start_date) >= today && !['rejected', 'cancelled'].includes(item.state))
    .sort((a, b) => a.start_date.localeCompare(b.start_date))[0];
  const nextLeaveStart = nextLeave ? toDate(nextLeave.start_date) : null;

  const firstName = user?.fullName?.trim().split(/\s+/)[0] || 'there';
  const roles = caps.data?.roles.map(roleName) ?? [];

  const destinations: Array<{ path: string; title: string; description: string; icon: AnimatedIcon }> = [
    { path: '/hrms/leave', title: 'Leave', description: 'Plan time away', icon: CalendarDaysIcon },
    { path: '/hrms/performance', title: 'Performance', description: 'Goals and reviews', icon: TrendingUpIcon },
    ...(has('project:view') ? [{ path: '/hrms/projects', title: 'Projects', description: 'Teams and allocations', icon: BriefcaseBusinessIcon }] : []),
    { path: '/hrms/content', title: 'Resources', description: 'Policies and holidays', icon: BookTextIcon },
  ];

  return <main className={`hrms-ws-page hrms-mywork${motion ? ' hrms-ws--motion' : ''}`}>
    <section className="hrms-mw-hero" aria-labelledby="hrms-mw-title">
      <div className="hrms-mw-greet">
        <LocalTime />
        <h1 id="hrms-mw-title">{greeting(new Date().getHours())}, <ShinyText text={firstName} disabled={!motion} /></h1>
        <p>Here’s what needs your attention today.</p>
        {roles.length > 0 && <ul className="hrms-mw-roles" aria-label="Your roles">{roles.map(role => <li key={role}>{role}</li>)}</ul>}
      </div>
      <div className="hrms-mw-art"><Illustration name="my-work" animate={motion} /></div>
      <aside className="hrms-mw-summary" aria-label="Summary">
        <div>
          <p className="hrms-mw-label">Waiting on you</p>
          {summaryLoading ? <p className="hrms-mw-total" aria-busy="true">…</p>
            : total > 0 ? <ActionDonut slices={sources.map(({ label, count }) => ({ label, count }))} />
            : <><p className="hrms-mw-clear"><CheckCircle2 size={20} aria-hidden="true" />You’re all caught up</p>
              <ul className="hrms-mw-breakdown">{sources.map(source => <li key={source.label}><span>{source.label}</span><b>{source.count}</b></li>)}</ul></>}
        </div>
        <div className="hrms-mw-leave">
          <p className="hrms-mw-label">Your next time off</p>
          {myLeave.isLoading ? <p>Loading…</p>
            : leaveUnavailable ? <p>Leave isn’t linked to this account — it has no employee profile.</p>
            : myLeave.isError ? <p>Couldn’t load your leave. <button type="button" className="hrms-mw-retry" onClick={() => void myLeave.refetch()}>Try again</button></p>
            : nextLeave && nextLeaveStart ? <p><strong>{formatDate(nextLeaveStart)}</strong> · {nextLeave.leave_type} <span className="hrms-mw-state" data-state={nextLeave.state}>{nextLeave.state}</span></p>
            : <p>Nothing planned yet. <Link to="/hrms/leave">Request leave<AnimIcon icon={ArrowRightIcon} size={14} /></Link></p>}
        </div>
      </aside>
    </section>

    <div className="hrms-mw-row">
    <nav className="hrms-mw-links" aria-label="Work shortcuts">
      {destinations.map(({ path, title, description, icon }) => <Link key={path} to={path} className="hrms-mw-link">
        <span className="hrms-mw-link-icon"><AnimIcon icon={icon} size={20} /></span>
        <span><strong>{title}</strong><small>{description}</small></span>
        <AnimIcon icon={ArrowRightIcon} size={16} className="hrms-mw-link-arrow" />
      </Link>)}
    </nav>
    <ComingUp />
    </div>

    <header className="hrms-mw-section">
      <div><h2>Tasks &amp; approvals</h2><p>Actions you can take, based on your role and assignments.</p></div>
      <Link className="hrms-outline-button" to="/hrms/workflows">View all workflows <ArrowRight size={16} aria-hidden="true" /></Link>
    </header>
    {caps.isError && <div role="alert" className="hrms-work-feedback"><p>Some work areas couldn’t be loaded.</p><button className="hrms-outline-button" onClick={() => void caps.refetch()}>Retry permissions</button></div>}
    <div className="hrms-work-panels">
      {(leaveApprovals.data?.length ?? 0) > 0 && <LeaveInbox items={pendingLeave} loading={leaveApprovals.isLoading} error={leaveApprovals.isError ? getApiErrorMessage(leaveApprovals.error) : undefined} retry={() => void leaveApprovals.refetch()} />}
      <CockpitInbox />
      <ProjectInbox />
      <WorkPanel title="Onboarding tasks" description="Help new colleagues get started." icon={UserRoundPlus} count={onboardingActions.length} loading={onboarding.isLoading} error={onboarding.isError ? getApiErrorMessage(onboarding.error) : undefined} retry={() => void onboarding.refetch()} empty="No onboarding tasks are waiting for you.">
        <ul>{onboardingActions.map(a => <li className="hrms-work-item" key={`${a.caseId}-${a.sequence}`}><p className="hrms-work-item-context">{a.employee}</p><h3>{a.title}</h3><p>Assigned to {a.owner_name}{a.due_date ? ` · Due ${a.due_date}` : ''}</p><Link className="hrms-outline-button" to={`/hrms/workflows?case=${a.caseId}`}>Open task <ArrowRight size={15} aria-hidden="true" /></Link></li>)}</ul>
      </WorkPanel>
    </div>
  </main>;
}
