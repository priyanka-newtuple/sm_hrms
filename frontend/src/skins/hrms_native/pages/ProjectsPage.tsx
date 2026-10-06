import { BriefcaseBusiness, ArrowRight, Plus, Search, Users } from 'lucide-react';
import { WorkPanel } from '../components/WorkPanel';
import { useHrmsCapabilities } from '../capabilities';
import { WorkflowStages, useWorkflowConfiguration, transitionLabel } from '../workflows/WorkflowConfiguration';
import { ConfiguredForm, ConfiguredField } from '../forms/ConfiguredForm';
import { useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { getApiErrorMessage, request } from '@/core/services/api/client';
import { PageHero } from '../components/PageHero';

type Data = Record<string, unknown>;
export type Item = { id: string; kind: string; state: string; data: Data; actions: string[]; project_name: string };
type Board = { projects: Item[]; allocations: Item[]; requests: Item[]; can_create: boolean; can_create_customer: boolean };
type Choice = { id: string; name: string };
type Options = { customers: Choice[]; pms: Choice[]; dms: Choice[]; approvers: Choice[]; employees: Choice[]; project_roles: Choice[] };
type Body = { action: string; data: Data; expected_revision: number; idempotency_key: string };
type Pending = Body & { target: string };
const label = (s: string) => s.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase());
const val = (d: Data, k: string) => String(d[k] ?? '');
const input = 'hrms-field-input';
export const PROJECT_KINDS = ['HRMS.Project', 'HRMS.ProjectChange', 'HRMS.Allocation', 'HRMS.AllocationChange'];
export const useProjects = () => { const caps=useHrmsCapabilities(); return useQuery({ queryKey: ['hrms', 'projects'], queryFn: () => request<Board>('/hrms/projects'), enabled: caps.data?.capabilities.includes('project:view') ?? false }); };
const projectKeys = ['name','description','customer_id','pm_id','dm_id','start_date','end_date','engagement_type','practice','health','currency','budget_amount','billing_rate','planned_hours'];
const allocationKeys = ['employee_id','project_role_id','start_date','end_date','percentage','billable','billing_rate'];

export function ProjectAction({ item, action, done }: { item?: Item; action: string; done: () => void }) {
  const proposed = (item?.data.proposed ?? item?.data ?? {}) as Data;
  const projectForm = ['create_project','propose_amendment'].includes(action) || (action === 'edit_request' && item?.kind === 'HRMS.ProjectChange');
  const allocationForm = ['request_allocation','amend_allocation'].includes(action) || (action === 'edit_request' && item?.kind === 'HRMS.AllocationChange');
  const [data, setData] = useState<Data>(() => ({ ...Object.fromEntries((projectForm ? projectKeys : allocationForm ? allocationKeys : []).filter(k => proposed[k] !== undefined).map(k => [k, proposed[k]])),
    ...(action === 'edit_request' ? { approver_id: item?.data.approver_id, note: item?.data.note } : {}) }));
  const [pending, setPending] = useState<Body | null>(null);
  const [preview, setPreview] = useState<{ segments: {start_date:string;end_date:string;committed:number;proposed:number;total:number}[]; over_capacity:boolean } | null>(null);
  const queryClient = useQueryClient();
  const options = useQuery({ queryKey: ['hrms','project-options'], staleTime: 0, refetchOnMount: 'always', queryFn: () => request<Options>('/hrms/projects/options'), enabled: projectForm || allocationForm || action === 'release_allocation' });
  const mutation = useMutation({ mutationFn: (body: Body) => request(item ? `/hrms/projects/${item.id}/actions` : '/hrms/projects/actions', { method:'POST', body:JSON.stringify(body) }),
    onSuccess: async () => { await queryClient.invalidateQueries({queryKey:['hrms']}); done(); },
    onError: async (error, body) => {
      const status=(error as Error & {status?:number}).status;
      if ([403,404,422].includes(status ?? 0)) setPending(null);
      if (status===409) {
        const operations=await request<Pending[]>('/hrms/projects/pending-actions');
        if (!operations.some(op=>op.idempotency_key===body.idempotency_key)) setPending(null);
        await queryClient.invalidateQueries({queryKey:['hrms']});
      }
    } });
  const previewMutation = useMutation({ mutationFn: () => {
    const projectId = item?.kind === 'HRMS.Project' ? item.id : val(item?.data ?? {},'project_id');
    const allocationId = item?.kind === 'HRMS.Allocation' ? item.id : val(item?.data ?? {},'allocation_id');
    return request<NonNullable<typeof preview>>(`/hrms/projects/${projectId}/capacity${allocationId ? `?allocation_id=${allocationId}` : ''}`, {method:'POST',body:JSON.stringify({action:'preview',data,idempotency_key:crypto.randomUUID()})});
  }, onSuccess: setPreview });
  function field(key: string, type='text', required=true) {
    return <ConfiguredField key={key} field={key} label={label(key)}><input type={type} required={required} className={input} min={type==='number'?0:undefined} step={type==='number'?'any':undefined} maxLength={4000} value={val(data,key)} onChange={e=>{setData({...data,[key]:type==='number'?Number(e.target.value):e.target.value});setPreview(null);}} /></ConfiguredField>;
  }
  function select(key: string, choices: Choice[], required=true) {
    return <ConfiguredField field={key} label={label(key.replace(/_id$/, ""))}><select required={required} className={input} value={val(data,key)} onChange={e=>{setData({...data,[key]:e.target.value || null});setPreview(null);}}><option value="">Select…</option>{choices.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></ConfiguredField>;
  }
  function enumeration(key:string, values:string[]) {return select(key,values.map(v=>({id:v,name:label(v)})),false);}
  function submit(e:FormEvent) {e.preventDefault();const body=pending ?? {action,data,expected_revision:Number(item?.data.revision ?? 0),idempotency_key:crypto.randomUUID()};setPending(body);mutation.mutate(body);}
  const entityType = projectForm ? 'HRMS.Project' : allocationForm ? 'HRMS.Allocation' : action === 'create_customer' ? 'HRMS.Customer' : item?.kind ?? 'HRMS.Project';
  return <ConfiguredForm entityType={entityType} aliases={{pm_id:'pm_name',dm_id:'dm_name',customer_id:'customer_name',employee_id:'employee_name',project_role_id:'project_role_name',approver_id:'approver_name'}}><form onSubmit={submit} className="hrms-surface hrms-people-form hrms-project-form"><h3 className="hrms-section-heading">{label(action)}</h3>
    <fieldset disabled={Boolean(pending)||mutation.isPending} className="grid gap-5 disabled:opacity-60 sm:grid-cols-2">
      {action==='create_customer' && <>{field('name')}{field('contact_name','text',false)}{field('contact_email','email',false)}{field('currency','text',false)}{field('contract_value','number',false)}</>}
      {projectForm && <>{field('name')}{field('description','text',false)}{select('customer_id',options.data?.customers??[])}{select('pm_id',options.data?.pms??[])}{select('dm_id',options.data?.dms??[])}{select('approver_id',options.data?.approvers??[])}{field('start_date','date')}{field('end_date','date')}{enumeration('engagement_type',['time_material','fixed_price','internal'])}{field('practice','text',false)}{enumeration('health',['green','amber','red'])}{field('currency','text',false)}{field('budget_amount','number',false)}{field('billing_rate','number',false)}{field('planned_hours','number',false)}{field('note','text',false)}</>}
      {allocationForm && <>{select('employee_id',options.data?.employees??[])}{select('project_role_id',options.data?.project_roles??[])}{field('start_date','date')}{field('end_date','date')}{field('percentage','number')}{enumeration('billable',['yes','no'])}{field('billing_rate','number',false)}{select('approver_id',options.data?.approvers??[],false)}{field('note','text',false)}<p className="text-sm text-muted-foreground sm:col-span-2">The project Delivery Manager approves. If you are that DM, choose an independent approver. A capacity exception requires a reason. Pending requests do not book capacity.</p></>}
      {action==='release_allocation' && <>{select('approver_id',options.data?.approvers??[],false)}{field('note')}<p className="text-sm sm:col-span-2">After approval, this allocation is cancelled and its capacity is released. Its history is retained.</p></>}
      {['reject','request_changes'].includes(action) && field('comment')}
      {action==='approve' && <p className="sm:col-span-2 text-sm">Approve this version and apply its proposed values. Capacity and project dates are checked again before committing.</p>}
    </fieldset>
    {options.isLoading && <p>Loading choices…</p>}{options.isError && <p role="alert">{getApiErrorMessage(options.error)}</p>}
    {allocationForm && <Button className="hrms-outline-button" type="button" variant="outline" disabled={Boolean(pending)||previewMutation.isPending} onClick={()=>previewMutation.mutate()}>Preview capacity</Button>}
    {previewMutation.isError && <p role="alert">{getApiErrorMessage(previewMutation.error)}</p>}
    {preview && <div className="hrms-notice"><p className="font-medium">{preview.over_capacity?'Capacity exception approval required':'Within capacity'}</p>{preview.segments.map(s=><p key={s.start_date}>{s.start_date} – {s.end_date}: {s.committed}% committed + {s.proposed}% proposed = {s.total}%</p>)}</div>}
    {mutation.isError && <p role="alert" className="text-sm text-destructive">{getApiErrorMessage(mutation.error)}{pending && ' Retry retains this exact request. Incomplete operations can also be resumed from Projects.'}</p>}
    <div className="hrms-form-actions"><Button className="hrms-primary-button" variant="primary" type="submit" disabled={mutation.isPending}>{mutation.isPending?'Saving…':pending?'Retry action':label(action)}</Button><Button className="hrms-outline-button" type="button" variant="outline" disabled={Boolean(pending)} onClick={done}>Cancel</Button></div>
  </form></ConfiguredForm>;
}

export function ProjectControls() {
  const board=useProjects();
  const [action,setAction]=useState<string|null>(null);
  return <div className="hrms-project-controls">
    <PageHero eyebrow="Build together" title="Projects" intro="A clear view of your projects, people, and delivery." illustration="projects"
      actions={<>{board.data?.can_create && <button type="button" className="hrms-primary-button" onClick={()=>setAction('create_project')}><Plus size={16} aria-hidden="true" />Add project</button>}{board.data?.can_create_customer && <button type="button" className="hrms-outline-button" onClick={()=>setAction('create_customer')}><Plus size={16} aria-hidden="true" />Add customer</button>}</>}
      stats={board.data ? [
        { label: 'Projects', value: board.data.projects.length },
        { label: 'Active', value: board.data.projects.filter(p => p.state === 'active').length, tone: 'positive' },
        { label: 'People allocated', value: new Set(board.data.allocations.filter(a => ['planned', 'active'].includes(a.state)).map(a => val(a.data, 'employee_id'))).size },
        { label: 'Pending approvals', value: board.data.requests.filter(r => r.state === 'pending').length, tone: 'attention' },
      ] : undefined} />
    {board.isError && <p role="alert">{getApiErrorMessage(board.error)}</p>}
    <Sheet open={Boolean(action)} onOpenChange={open=>{if(!open)setAction(null);}}><SheetContent className="hrms-brand hrms-review-drawer overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-4xl"><SheetHeader><SheetTitle>{action === 'create_customer' ? 'Add customer' : 'Create project'}</SheetTitle></SheetHeader>{action && <div className="p-6"><ProjectAction key={action} action={action} done={()=>setAction(null)} /></div>}</SheetContent></Sheet>
    <ProjectRecovery />
  </div>;
}

export function ProjectRecovery() {
  const caps=useHrmsCapabilities();
  const pending=useQuery({enabled:caps.data?.capabilities.includes('project:view')??false,queryKey:['hrms','project-pending'],queryFn:()=>request<Pending[]>('/hrms/projects/pending-actions')});
  const client=useQueryClient();
  const resume=useMutation({mutationFn:(p:Pending)=>{const {target,...body}=p;return request(target==='new'?'/hrms/projects/actions':`/hrms/projects/${target}/actions`,{method:'POST',body:JSON.stringify(body)});},onSuccess:()=>client.invalidateQueries({queryKey:['hrms']})});
  return <div>
    {pending.data?.map(p=><div key={p.idempotency_key} className="hrms-notice">Incomplete {label(p.action)} <Button className="hrms-outline-button" variant="outline" disabled={resume.isPending} onClick={()=>resume.mutate(p)}>Resume operation</Button></div>)}
    {resume.isError && <p role="alert">{getApiErrorMessage(resume.error)}</p>}
    {pending.isError && <p role="alert">Unable to load unfinished operations. <button className="hrms-text-link" onClick={()=>void pending.refetch()}>Retry</button></p>}
  </div>;
}

export function ProjectInbox() {
  const board=useProjects();
  const caps=useHrmsCapabilities();
  const actions=board.data?.requests.filter(r=>r.state==='pending' && r.actions.includes('approve'))??[];
  if (!caps.data?.capabilities.includes('project:view')) return null;
  return <WorkPanel title="Projects & allocations" description="Review changes and resource requests." icon={BriefcaseBusiness} count={actions.length} loading={board.isLoading} error={board.isError ? getApiErrorMessage(board.error) : undefined} retry={() => void board.refetch()} empty="No project or allocation approvals are waiting for you.">
    <ul>{actions.map(r=><li className="hrms-work-item" key={r.id}><p className="hrms-work-item-context">{r.kind==='HRMS.ProjectChange'?'Project approval':'Allocation approval'}</p><h3>{r.project_name}</h3><p>Requested by {val(r.data,'requested_by_name')}</p><Link className="hrms-outline-button" to={`/hrms/workflows?case=${r.id}`}>Review request <ArrowRight size={15} aria-hidden="true" /></Link></li>)}</ul>
  </WorkPanel>;
}

function ReadableData({ data }: {data:Data}) {
  return <dl className="hrms-surface hrms-detail-grid">{Object.entries(data).filter(([k,v])=>v!=null && v!=='' && !k.endsWith('_id') && !['created_by','decided_by','proposed','revision','expected_revision','hrms_operation_key'].includes(k)).map(([k,v])=><div key={k}><dt className="text-xs text-muted-foreground">{label(k)}</dt><dd className="break-words text-sm">{String(v)}</dd></div>)}</dl>;
}

export function ProjectDetail({entityId}:{entityId:string}) {
  const query=useProjects();
  const workflowQuery=useWorkflowConfiguration();
  const configured=workflowQuery.data?.find(r=>r.entity_id===entityId);
  const [action,setAction]=useState<string|null>(null);
  const board=query.data;
  const item=[...(board?.projects??[]),...(board?.requests??[]),...(board?.allocations??[])].find(r=>r.id===entityId);
  if(query.isError) return <p role="alert" className="p-6">{getApiErrorMessage(query.error)}</p>;
  if(!item) return <p className="p-6">{query.isLoading?'Loading project…':'This project record is not available to your account.'}</p>;
  const project=board?.projects.find(p=>p.id===(item.kind==='HRMS.Project'?item.id:item.data.project_id));
  const source=item.kind==='HRMS.ProjectChange'?project:board?.allocations.find(a=>a.id===item.data.allocation_id);
  const proposed=item.data.proposed as Data|undefined;
  return <section className="hrms-brand hrms-project-detail"><div><h2 className="hrms-case-name">{item.project_name}</h2><p className="text-sm text-muted-foreground">{configured?.state_label ?? label(item.state)} · Revision {Number(item.data.revision??0)}</p></div>
    <WorkflowStages entityId={entityId} />
    <ReadableData data={item.data} />
    {proposed && <div className="hrms-surface hrms-table-scroll"><table className="hrms-people-table"><caption className="p-3 text-left font-medium">Current and proposed values</caption><thead><tr><th className="p-2">Field</th><th className="p-2">Current</th><th className="p-2">Proposed</th></tr></thead><tbody>{Object.entries(proposed).filter(([k])=>!k.endsWith('_id')).map(([k,v])=><tr key={k} className="border-t"><td className="p-2">{label(k)}</td><td className="p-2">{String(source?.data[k]??'—')}</td><td className="p-2">{String(v)}</td></tr>)}</tbody></table></div>}
    {item.state==='approved' && <p className="text-sm">{item.data.applied==='yes'?'Approved changes applied.':'Approved; application is incomplete. The original actor must resume the operation from Projects.'}</p>}
    {!action && <div className="flex flex-wrap gap-2">{item.actions.map(a=><Button key={a} variant="primary" onClick={()=>setAction(a)}>{transitionLabel(configured,a)}</Button>)}{!item.actions.length && <p className="text-sm text-muted-foreground">No action is available to you at this stage.</p>}</div>}
    {action && <ProjectAction key={`${item.id}:${action}`} item={item} action={action} done={()=>setAction(null)} />}
    {item.kind==='HRMS.Project' && <><h3 className="font-semibold">Team and allocations</h3>{board?.allocations.filter(a=>a.data.project_id===item.id).map(a=><p key={a.id} className="text-sm"><Link className="hrms-text-link" to={`/hrms/workflows?case=${a.id}`}>{val(a.data,'employee_name')} · {val(a.data,'project_role_name')} · {val(a.data,'percentage')}% · {label(a.state)}</Link></p>)}<h3 className="font-semibold">Approval history</h3>{board?.requests.filter(r=>r.data.project_id===item.id).map(r=><p key={r.id} className="text-sm"><Link className="hrms-text-link" to={`/hrms/workflows?case=${r.id}`}>{r.kind==='HRMS.ProjectChange'?'Project':'Allocation'} · {label(val(r.data,'kind'))} · {label(r.state)} · Approver: {val(r.data,'approver_name')}</Link></p>)}</>}
  </section>;
}


/** Project directory: one business record per row. Workflow work lives in Workflows. */
export default function ProjectsPage() {
  const query = useProjects();
  const configured = useWorkflowConfiguration();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [editing, setEditing] = useState(false);
  const [allocating,setAllocating]=useState(false);
  const caps=useHrmsCapabilities();
  const projects = query.data?.projects ?? [];
  const selected = projects.find(p => p.id === params.get('project'));
  const stateLabel = (p:Item) => configured.data?.find(r=>r.entity_id===p.id)?.state_label ?? label(p.state);
  const visible = projects.filter(p => (!status || p.state === status) &&
    [p.project_name, ...['identifier','customer_name','pm_name','dm_name'].map(k=>val(p.data,k))].join(' ').toLowerCase().includes(search.toLowerCase()));
  const editTarget = (project:Item) => {
    const draft = query.data?.requests.find(r=>r.kind==='HRMS.ProjectChange' && r.data.project_id===project.id && r.actions.includes('edit_request'));
    if (draft) return {item:draft, action:'edit_request'};
    if (project.actions.includes('propose_amendment')) return {item:project, action:'propose_amendment'};
    return undefined;
  };
  const edit = selected ? editTarget(selected) : undefined;
  const open = (project:Item, editMode=false) => {setParams({project:project.id});setEditing(editMode);setAllocating(false);};
  if(caps.isLoading) return <p className="p-6">Loading access…</p>;
  if(!caps.data?.capabilities.includes('project:view')) return <p role="alert" className="p-6">You do not have access to Projects.</p>;
  return <main className="hrms-workspace-page hrms-project-page">
    <ProjectControls />
    <div className="hrms-filter-bar">
      <label className="hrms-search"><Search size={18} aria-hidden="true" /><input aria-label="Search projects" placeholder="Search projects, customers or managers…" className={input} value={search} onChange={e=>setSearch(e.target.value)} /></label>
      <select aria-label="Project status" className={input} value={status} onChange={e=>setStatus(e.target.value)}><option value="">All statuses</option>{[...new Set(projects.map(p=>p.state))].map(state=><option key={state} value={state}>{stateLabel(projects.find(p=>p.state===state)!)}</option>)}</select>
    </div>
    {query.isLoading && <p role="status">Loading projects…</p>}
    {query.isError && <p role="alert">{getApiErrorMessage(query.error)}</p>}
    {query.data && <div className="hrms-surface hrms-directory">
      <div className="hrms-directory-heading"><span className="hrms-work-icon"><BriefcaseBusiness size={23} strokeWidth={1.25} /></span><div><h2>Project directory</h2><p>{visible.length} of {projects.length} projects</p></div></div><div className="hrms-table-scroll">
      <table className="hrms-people-table"><thead className="bg-muted/40"><tr>{['Project','Customer','Project Manager','Delivery Manager','Dates','Status','Actions'].map(h=><th key={h} className="p-3 font-medium">{h}</th>)}</tr></thead>
        <tbody>{visible.map(p=><tr key={p.id} className="border-t align-top">
          <td className="p-3"><button className="hrms-text-link" onClick={()=>open(p)}>{p.project_name}</button><p className="mt-1 text-xs text-muted-foreground">{val(p.data,'identifier')}</p></td>
          <td className="p-3">{val(p.data,'customer_name')||'—'}</td><td className="p-3">{val(p.data,'pm_name')||'—'}</td><td className="p-3">{val(p.data,'dm_name')||'—'}</td>
          <td className="whitespace-nowrap p-3">{val(p.data,'start_date')||'—'}<br />{val(p.data,'end_date')||'—'}</td><td className="p-3"><span className="hrms-status" data-state={p.state}>{stateLabel(p)}</span></td>
          <td className="p-3"><div className="flex gap-2"><Button className="hrms-outline-button" variant="outline" onClick={()=>open(p)}>View details</Button>{editTarget(p)&&<Button className="hrms-outline-button" variant="outline" onClick={()=>open(p,true)}>Edit</Button>}</div></td>
        </tr>)}{!visible.length&&<tr><td colSpan={7} className="p-8 text-center text-muted-foreground">{projects.length?'No projects match your filters.':'No projects are available in your scope.'}</td></tr>}</tbody>
      </table></div>
    </div>}
    <Sheet open={Boolean(selected)} onOpenChange={opened=>{if(!opened){setParams({});setEditing(false);setAllocating(false);}}}>
      <SheetContent className="hrms-brand hrms-review-drawer overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-4xl">
        <SheetHeader><SheetTitle>{selected?.project_name}</SheetTitle></SheetHeader>
        {selected&&<div className="hrms-project-detail">
          <div className="flex flex-wrap items-center gap-3"><span className="hrms-status" data-state={selected.state}>{stateLabel(selected)}</span>
            <Link className="hrms-text-link" to={`/hrms/workflows?case=${selected.id}`}>View workflow</Link>
            {!editing&&edit&&<Button className="hrms-primary-button" variant="primary" onClick={()=>{setEditing(true);setAllocating(false);}}>Edit project</Button>}
          </div>
          {selected.actions.includes('request_allocation') && <Button className="hrms-primary-button" variant="primary" onClick={()=>{setAllocating(true);setEditing(false);}}>Add allocation</Button>}
          {allocating && selected.actions.includes('request_allocation') && <><p className="text-sm text-muted-foreground">Choose an employee, project role, dates and capacity. The request goes to the project's Delivery Manager; self-approval is not permitted. Submit and track approval in Workflows.</p><ProjectAction key={`${selected.id}:allocation`} item={selected} action="request_allocation" done={()=>setAllocating(false)} /></>}
          {editing&&edit?<><p className="text-sm text-muted-foreground">Changes are saved as an approval request. Review and approve them in Workflows before they update the project.</p><ProjectAction key={`${edit.item.id}:${edit.action}`} item={edit.item} action={edit.action} done={()=>setEditing(false)} /></>:
            <ConfiguredForm entityType="HRMS.Project"><dl className="hrms-surface hrms-detail-grid">{Object.entries(selected.data).filter(([k,v])=>v!=null&&v!==''&&!k.endsWith('_id')&&!['created_by','revision','hrms_operation_key'].includes(k)).map(([key,v])=><div key={key}><ConfiguredField field={key} label={label(key)}><p className="whitespace-pre-wrap break-words font-medium">{String(v)}</p></ConfiguredField></div>)}</dl></ConfiguredForm>}
          <section className="hrms-surface hrms-project-team"><div className="hrms-panel-title"><span className="hrms-work-icon"><Users size={23} strokeWidth={1.25} /></span><h3 className="hrms-section-heading">Assigned team</h3><Link className="hrms-text-link" to={`/hrms/allocations?project=${selected.id}`}>View allocations</Link></div>
            {query.data?.allocations.filter(a=>a.data.project_id===selected.id).map(a=><div key={a.id} className="hrms-notice"><p className="font-medium">{val(a.data,'employee_name')} · {val(a.data,'project_role_name')}</p><p>{val(a.data,'percentage')}% · {val(a.data,'start_date')} to {val(a.data,'end_date')}</p></div>)}
            {!query.data?.allocations.some(a=>a.data.project_id===selected.id)&&<p className="text-sm text-muted-foreground">No allocations yet.</p>}
          </section>
          <p className="text-sm text-muted-foreground">Project stages, allocation requests and approvals are available in <Link className="hrms-text-link" to={`/hrms/workflows?case=${selected.id}`}>Workflows</Link>.</p>
        </div>}
      </SheetContent>
    </Sheet>
  </main>;
}
