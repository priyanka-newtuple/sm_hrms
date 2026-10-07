import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Grid2X2, Plus, Search } from 'lucide-react';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { getApiErrorMessage } from '@/core/services/api/client';
import { useHrmsCapabilities } from '../capabilities';
import { useWorkflowConfiguration } from '../workflows/WorkflowConfiguration';
import { ProjectAction, ProjectDetail, ProjectRecovery, useProjects, type Item } from './ProjectsPage';
import { PageHero } from '../components/PageHero';

const value = (item: Item, key: string) => String(item.data[key] ?? '');
const humanize = (text: string) => text.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase());

/** A second view of native allocation records, not a separate allocation store. */
export default function AllocationsPage() {
  const caps = useHrmsCapabilities();
  const query = useProjects();
  const configured = useWorkflowConfiguration();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [tab, setTab] = useState<'allocations' | 'requests'>('allocations');
  const [creating, setCreating] = useState(false);
  const [projectId, setProjectId] = useState('');
  const projectFilter = params.get('project') ?? '';
  const allocations = query.data?.allocations ?? [];
  const requests = query.data?.requests.filter(item => item.kind === 'HRMS.AllocationChange') ?? [];
  const projects = query.data?.projects ?? [];
  const eligible = projects.filter(project => project.actions.includes('request_allocation'));
  const target = eligible.find(project => project.id === projectId);
  const selected = allocations.find(item => item.id === params.get('allocation'));
  const rows = tab === 'allocations' ? allocations : requests;
  const display = (item: Item, key: string) => String(
    (tab === 'requests' ? (item.data.proposed as Record<string, unknown> | undefined)?.[key] : undefined)
    ?? item.data[key] ?? '');
  const stateLabel = (item: Item) => configured.data?.find(row => row.entity_id === item.id)?.state_label ?? humanize(item.state);
  const visible = rows.filter(item => (!projectFilter || value(item, 'project_id') === projectFilter)
    && (!status || item.state === status)
    && [item.project_name, value(item, 'identifier'), display(item, 'employee_name'), display(item, 'project_role_name')]
      .join(' ').toLowerCase().includes(search.toLowerCase()));
  const chooseProjectFilter = (id: string) => {
    const next = new URLSearchParams(params);
    if (id) next.set('project', id); else next.delete('project');
    setParams(next);
  };
  const closeDetail = () => { const next = new URLSearchParams(params); next.delete('allocation'); setParams(next); };

  if (caps.isPending) return <p className="p-6" role="status">Loading allocation access…</p>;
  if (caps.isError) return <div className="p-6" role="alert">Unable to load access. <button onClick={() => void caps.refetch()}>Retry</button></div>;
  if (!caps.data.capabilities.includes('project:view')) return <p className="p-6" role="alert">You do not have access to Allocations.</p>;

  return <main className="hrms-workspace-page hrms-project-page">
    <PageHero title="Allocations" intro="See who is working where, and plan the next assignment." illustration="allocations"
      actions={eligible.length > 0 && <button className="hrms-primary-button" onClick={() => {
        setProjectId(eligible.some(p => p.id === projectFilter) ? projectFilter : eligible.length === 1 ? eligible[0].id : '');
        setCreating(true);
      }}><Plus size={16} aria-hidden="true" />Add allocation</button>}
      stats={query.isSuccess ? [
        { label: 'Allocations', value: allocations.length },
        { label: 'Active', value: allocations.filter(item => item.state === 'active').length, tone: 'positive' },
        { label: 'Planned', value: allocations.filter(item => item.state === 'planned').length },
        { label: 'Pending requests', value: requests.filter(item => item.state === 'pending').length, tone: 'attention' },
      ] : undefined} />
    <ProjectRecovery />
    <div className="flex flex-wrap gap-3 mb-6" role="group" aria-label="Allocation views">
      <button className={tab === 'allocations' ? 'hrms-primary-button' : 'hrms-outline-button'} aria-pressed={tab === 'allocations'} onClick={() => {setTab('allocations'); setStatus('');}}>Allocations</button>
      <button className={tab === 'requests' ? 'hrms-primary-button' : 'hrms-outline-button'} aria-pressed={tab === 'requests'} onClick={() => {setTab('requests'); setStatus('');}}>Requests</button>
    </div>
    <div className="hrms-filter-bar">
      <label className="hrms-search"><Search size={18} aria-hidden="true" /><input className="hrms-field-input" aria-label="Search allocations" placeholder="Search employee, project or role…" value={search} onChange={event => setSearch(event.target.value)} /></label>
      <select className="hrms-field-input" aria-label="Filter by project" value={projectFilter} onChange={event => chooseProjectFilter(event.target.value)}><option value="">All projects</option>{projectFilter && !projects.some(p => p.id === projectFilter) && <option value={projectFilter}>Unavailable project</option>}{projects.map(project => <option key={project.id} value={project.id}>{project.project_name}</option>)}</select>
      <select className="hrms-field-input" aria-label="Allocation status" value={status} onChange={event => setStatus(event.target.value)}><option value="">All statuses</option>{[...new Set(rows.map(item => item.state))].map(state => <option key={state} value={state}>{stateLabel(rows.find(item => item.state === state)!)}</option>)}</select>
    </div>
    {query.isPending && <p role="status">Loading allocations…</p>}
    {query.isError && <div role="alert">{getApiErrorMessage(query.error)} <button className="hrms-text-link" onClick={() => void query.refetch()}>Retry</button></div>}
    {configured.isError && <p role="alert">Workflow labels could not be refreshed. <button className="hrms-text-link" onClick={() => void configured.refetch()}>Retry</button></p>}
    {query.isSuccess && <section className="hrms-surface hrms-directory">
      <div className="hrms-directory-heading"><span className="hrms-work-icon"><Grid2X2 size={23} strokeWidth={1.25} aria-hidden="true" /></span><div><h2>{tab === 'allocations' ? 'Allocation directory' : 'Allocation requests'}</h2><p>{visible.length} of {rows.length} {tab} in your scope</p></div></div>
      {tab === 'requests' && <p className="px-6 py-3 text-sm text-slate-600">Requests do not reserve capacity. Submit and review approvals in Workflows.</p>}
      <div className="hrms-table-scroll"><table className="hrms-people-table"><thead><tr>{['Employee', 'Project', 'Project role', 'Dates', 'Allocation', 'Status', 'Actions'].map(title => <th key={title} scope="col">{title}</th>)}</tr></thead>
        <tbody>{visible.map(item => <tr key={item.id}>
          <td>{display(item, 'employee_name') || '—'}<p className="mt-1 text-xs text-slate-500">{value(item, 'identifier')}</p></td>
          <td><Link className="hrms-text-link" to={`/hrms/projects?project=${value(item, 'project_id')}`}>{item.project_name}</Link></td>
          <td>{display(item, 'project_role_name') || '—'}</td><td className="whitespace-nowrap">{display(item, 'start_date') || '—'}<br />{display(item, 'end_date') || '—'}</td>
          <td>{display(item, 'percentage') ? `${display(item, 'percentage')}%` : '—'}</td><td><span className="hrms-status" data-state={item.state}>{stateLabel(item)}</span></td>
          <td>{tab === 'requests' ? <Link className="hrms-outline-button" to={`/hrms/workflows?case=${item.id}`}>View request</Link> : <button className="hrms-outline-button" onClick={() => {const next = new URLSearchParams(params); next.set('allocation', item.id); setParams(next);}}>View details</button>}</td>
        </tr>)}{!visible.length && <tr><td colSpan={7} className="p-8 text-center text-slate-500">{rows.length ? 'No allocations match your filters.' : tab === 'requests' ? 'No allocation requests are available in your scope.' : 'No allocations yet. Approved allocation requests will appear here.'}</td></tr>}</tbody>
      </table></div>
    </section>}
    {params.has('allocation') && query.isSuccess && !selected && <p role="alert">This allocation is not available to your account. <button onClick={closeDetail}>Dismiss</button></p>}
    <Sheet open={Boolean(selected)} onOpenChange={open => {if (!open) closeDetail();}}><SheetContent className="hrms-brand hrms-review-drawer overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-4xl"><SheetHeader><SheetTitle>Allocation details</SheetTitle></SheetHeader>{selected && <ProjectDetail key={selected.id} entityId={selected.id} />}</SheetContent></Sheet>
    <Sheet open={creating} onOpenChange={setCreating}><SheetContent className="hrms-brand hrms-review-drawer overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-4xl"><SheetHeader><SheetTitle>Add allocation</SheetTitle></SheetHeader>
      <div className="p-6 space-y-5"><p className="text-sm text-slate-600">Choose a project you manage. Save a request, then submit it for independent approval in Workflows.</p>
        <label className="block space-y-2"><span>Project</span><select className="hrms-field-input" value={projectId} onChange={event => setProjectId(event.target.value)}><option value="">Choose a project…</option>{eligible.map(project => <option key={project.id} value={project.id}>{project.project_name}</option>)}</select></label>
        {target && <ProjectAction key={target.id} item={target} action="request_allocation" done={() => {setCreating(false); setTab('requests'); setStatus(''); setSearch(''); chooseProjectFilter(target.id);}} />}
        {!eligible.length && <p>No project is currently available for an allocation request.</p>}
      </div>
    </SheetContent></Sheet>
  </main>;
}
