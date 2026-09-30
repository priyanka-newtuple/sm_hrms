import { useQuery } from '@tanstack/react-query';
import { ArrowRight, ArrowUpRight, BriefcaseBusiness, CalendarDays, TrendingUp, UserRoundPlus } from 'lucide-react';
import { Link } from 'react-router-dom';
import { request, getApiErrorMessage } from '@/core/services/api/client';
import { useHrmsCapabilities } from '../capabilities';
import { WorkPanel } from '../components/WorkPanel';
import { CockpitInbox } from './CockpitPage';
import { ProjectInbox } from './ProjectsPage';

type WorkCase = { entity_id: string; employee_name: string; steps: { sequence: number; title: string; owner_name: string; can_complete: boolean; due_date: string | null }[] };

export default function MyWorkPage() {
  const caps = useHrmsCapabilities();
  const query = useQuery({ queryKey: ['hrms', 'my-work'], queryFn: () => request<WorkCase[]>('/hrms/onboarding') });
  const actions = query.data?.flatMap(c => c.steps.filter(s => s.can_complete).map(s => ({ ...s, caseId: c.entity_id, employee: c.employee_name }))) ?? [];
  const destinations = [
    { path: '/hrms/leave', title: 'Leave requests', description: 'Plan time away and review team requests.', icon: CalendarDays },
    { path: '/hrms/performance', title: 'Performance', description: 'Keep goals, reviews, and development moving.', icon: TrendingUp },
    ...(caps.data?.capabilities.includes('project:view') ? [{ path: '/hrms/projects', title: 'Projects', description: 'Explore your projects and team allocations.', icon: BriefcaseBusiness }] : []),
  ];
  return <main className="hrms-workspace-page">
    <header className="hrms-workspace-heading"><div><p className="hrms-eyebrow">YOUR WORKSPACE</p><h1>Quick actions</h1><p className="hrms-intro">A clear view of what needs your attention.</p></div><Link className="hrms-outline-button" to="/hrms/workflows">View workflows <ArrowRight size={16} aria-hidden="true" /></Link></header>
    <nav className="hrms-work-shortcuts" aria-label="Work shortcuts">{destinations.map(({path,title,description,icon:Icon}) => <Link key={path} className="hrms-resource-card" to={path}><Icon size={26} strokeWidth={1.25} aria-hidden="true" /><ArrowUpRight className="hrms-card-arrow" size={18} aria-hidden="true" /><h2>{title}</h2><p>{description}</p></Link>)}</nav>
    <div className="hrms-work-section-title"><h2>Your tasks & approvals</h2><p>Available actions are based on your role and assignments.</p></div>
    {caps.isLoading && <p role="status">Loading permissions…</p>}
    {caps.isError && <div role="alert" className="hrms-work-feedback"><p>Some work areas couldn’t be loaded.</p><button className="hrms-outline-button" onClick={() => void caps.refetch()}>Retry permissions</button></div>}
    <div className="hrms-work-panels"><CockpitInbox /><ProjectInbox />
      <WorkPanel title="Onboarding tasks" description="Help new colleagues get started." icon={UserRoundPlus} count={actions.length} loading={query.isLoading} error={query.isError ? getApiErrorMessage(query.error) : undefined} retry={() => void query.refetch()} empty="No onboarding tasks are waiting for you.">
        <ul>{actions.map(a => <li className="hrms-work-item" key={`${a.caseId}-${a.sequence}`}><p className="hrms-work-item-context">{a.employee}</p><h3>{a.title}</h3><p>Assigned to {a.owner_name}{a.due_date ? ` · Due ${a.due_date}` : ''}</p><Link className="hrms-outline-button" to={`/hrms/workflows?case=${a.caseId}`}>Open task <ArrowRight size={15} aria-hidden="true" /></Link></li>)}</ul>
      </WorkPanel>
    </div>
  </main>;
}
