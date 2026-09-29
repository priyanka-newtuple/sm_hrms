import { WorkflowStages, useWorkflowConfiguration, transitionLabel } from '../workflows/WorkflowConfiguration';
import { ConfiguredForm, ConfiguredField } from '../forms/ConfiguredForm';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { getApiErrorMessage, request } from '@/core/services/api/client';

type Data = Record<string, unknown>;
type Item = { id: string; kind: string; state: string; data: Data; actions: string[]; project_name: string };
type Board = { projects: Item[]; allocations: Item[]; requests: Item[]; can_create: boolean; can_create_customer: boolean };
type Choice = { id: string; name: string };
type Options = { customers: Choice[]; pms: Choice[]; dms: Choice[]; approvers: Choice[]; employees: Choice[]; project_roles: Choice[] };
type Body = { action: string; data: Data; expected_revision: number; idempotency_key: string };
type Pending = Body & { target: string };
const label = (s: string) => s.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase());
const val = (d: Data, k: string) => String(d[k] ?? '');
const input = 'w-full rounded-lg border border-border bg-background p-2 text-sm';
export const PROJECT_KINDS = ['HRMS.Project', 'HRMS.ProjectChange', 'HRMS.Allocation', 'HRMS.AllocationChange'];
const useProjects = () => useQuery({ queryKey: ['hrms', 'projects'], queryFn: () => request<Board>('/hrms/projects') });
const projectKeys = ['name','description','customer_id','pm_id','dm_id','start_date','end_date','engagement_type','practice','health','currency','budget_amount','billing_rate','planned_hours'];
const allocationKeys = ['employee_id','project_role_id','start_date','end_date','percentage','billable','billing_rate'];

function ProjectAction({ item, action, done }: { item?: Item; action: string; done: () => void }) {
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
  return <ConfiguredForm entityType={entityType} aliases={{pm_id:'pm_name',dm_id:'dm_name',customer_id:'customer_name',employee_id:'employee_name',project_role_id:'project_role_name',approver_id:'approver_name'}}><form onSubmit={submit} className="space-y-4 rounded-xl border bg-background p-5"><h3 className="font-semibold">{label(action)}</h3>
    <fieldset disabled={Boolean(pending)||mutation.isPending} className="grid gap-3 disabled:opacity-60 sm:grid-cols-2">
      {action==='create_customer' && <>{field('name')}{field('contact_name','text',false)}{field('contact_email','email',false)}{field('currency','text',false)}{field('contract_value','number',false)}</>}
      {projectForm && <>{field('name')}{field('description','text',false)}{select('customer_id',options.data?.customers??[])}{select('pm_id',options.data?.pms??[])}{select('dm_id',options.data?.dms??[])}{select('approver_id',options.data?.approvers??[])}{field('start_date','date')}{field('end_date','date')}{enumeration('engagement_type',['time_material','fixed_price','internal'])}{field('practice','text',false)}{enumeration('health',['green','amber','red'])}{field('currency','text',false)}{field('budget_amount','number',false)}{field('billing_rate','number',false)}{field('planned_hours','number',false)}{field('note','text',false)}</>}
      {allocationForm && <>{select('employee_id',options.data?.employees??[])}{select('project_role_id',options.data?.project_roles??[])}{field('start_date','date')}{field('end_date','date')}{field('percentage','number')}{enumeration('billable',['yes','no'])}{field('billing_rate','number',false)}{select('approver_id',options.data?.approvers??[],false)}{field('note','text',false)}<p className="text-sm text-muted-foreground sm:col-span-2">The project Delivery Manager approves. If you are that DM, choose an independent approver. A capacity exception requires a reason. Pending requests do not book capacity.</p></>}
      {action==='release_allocation' && <>{select('approver_id',options.data?.approvers??[],false)}{field('note')}<p className="text-sm sm:col-span-2">After approval, this allocation is cancelled and its capacity is released. Its history is retained.</p></>}
      {['reject','request_changes'].includes(action) && field('comment')}
      {action==='approve' && <p className="sm:col-span-2 text-sm">Approve this version and apply its proposed values. Capacity and project dates are checked again before committing.</p>}
    </fieldset>
    {options.isLoading && <p>Loading choices…</p>}{options.isError && <p role="alert">{getApiErrorMessage(options.error)}</p>}
    {allocationForm && <Button type="button" variant="outline" disabled={Boolean(pending)||previewMutation.isPending} onClick={()=>previewMutation.mutate()}>Preview capacity</Button>}
    {previewMutation.isError && <p role="alert">{getApiErrorMessage(previewMutation.error)}</p>}
    {preview && <div className="rounded-lg border p-3 text-sm"><p className="font-medium">{preview.over_capacity?'Capacity exception approval required':'Within capacity'}</p>{preview.segments.map(s=><p key={s.start_date}>{s.start_date} – {s.end_date}: {s.committed}% committed + {s.proposed}% proposed = {s.total}%</p>)}</div>}
    {mutation.isError && <p role="alert" className="text-sm text-destructive">{getApiErrorMessage(mutation.error)}{pending && ' Retry retains this exact request. Incomplete operations can also be resumed from Projects.'}</p>}
    <div className="flex gap-2"><Button variant="primary" type="submit" disabled={mutation.isPending}>{mutation.isPending?'Saving…':pending?'Retry action':label(action)}</Button><Button type="button" variant="outline" disabled={Boolean(pending)} onClick={done}>Cancel</Button></div>
  </form></ConfiguredForm>;
}

export function ProjectControls() {
  const board=useProjects();
  const [action,setAction]=useState<string|null>(null);
  const pending=useQuery({queryKey:['hrms','project-pending'],queryFn:()=>request<Pending[]>('/hrms/projects/pending-actions')});
  const client=useQueryClient();
  const resume=useMutation({mutationFn:(p:Pending)=>{const {target,...body}=p;return request(target==='new'?'/hrms/projects/actions':`/hrms/projects/${target}/actions`,{method:'POST',body:JSON.stringify(body)});},onSuccess:()=>client.invalidateQueries({queryKey:['hrms']})});
  return <div className="space-y-3">
    <div className="flex gap-2">{board.data?.can_create && <Button variant="primary" onClick={()=>setAction('create_project')}>Create project</Button>}{board.data?.can_create_customer && <Button variant="outline" onClick={()=>setAction('create_customer')}>Add customer</Button>}</div>
    {board.isError && <p role="alert">{getApiErrorMessage(board.error)}</p>}
    {action && <ProjectAction key={action} action={action} done={()=>setAction(null)} />}
    {pending.data?.map(p=><div key={p.idempotency_key} className="rounded-lg border p-3 text-sm">Incomplete {label(p.action)} <Button variant="outline" disabled={resume.isPending} onClick={()=>resume.mutate(p)}>Resume operation</Button></div>)}
    {resume.isError && <p role="alert">{getApiErrorMessage(resume.error)}</p>}
  </div>;
}

export function ProjectInbox() {
  const board=useProjects();
  const actions=board.data?.requests.filter(r=>r.state==='pending' && r.actions.includes('approve'))??[];
  return <section className="space-y-2"><h2 className="font-semibold">Project and allocation approvals</h2>
    {board.isLoading && <p>Loading approvals…</p>}{board.isError && <p role="alert">{getApiErrorMessage(board.error)}</p>}
    {!board.isLoading && !board.isError && !actions.length && <p className="text-sm text-muted-foreground">No project or allocation approvals are waiting for you.</p>}
    {actions.map(r=><Link key={r.id} className="block rounded-xl border bg-background p-4 text-sm" to={`/hrms/workflows?case=${r.id}`}>{r.project_name} · {r.kind==='HRMS.ProjectChange'?'Project approval':'Allocation approval'} · Requested by {val(r.data,'requested_by_name')}</Link>)}
  </section>;
}

function ReadableData({ data }: {data:Data}) {
  return <dl className="grid gap-3 sm:grid-cols-2">{Object.entries(data).filter(([k,v])=>v!=null && v!=='' && !k.endsWith('_id') && !['created_by','decided_by','proposed','revision','expected_revision','hrms_operation_key'].includes(k)).map(([k,v])=><div key={k}><dt className="text-xs text-muted-foreground">{label(k)}</dt><dd className="break-words text-sm">{String(v)}</dd></div>)}</dl>;
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
  return <section className="space-y-5 p-6"><div><h2 className="text-xl font-semibold">{item.project_name}</h2><p className="text-sm text-muted-foreground">{configured?.state_label ?? label(item.state)} · Revision {Number(item.data.revision??0)}</p></div>
    <WorkflowStages entityId={entityId} />
    <ReadableData data={item.data} />
    {proposed && <div className="overflow-auto rounded-lg border"><table className="w-full text-left text-sm"><caption className="p-3 text-left font-medium">Current and proposed values</caption><thead><tr><th className="p-2">Field</th><th className="p-2">Current</th><th className="p-2">Proposed</th></tr></thead><tbody>{Object.entries(proposed).filter(([k])=>!k.endsWith('_id')).map(([k,v])=><tr key={k} className="border-t"><td className="p-2">{label(k)}</td><td className="p-2">{String(source?.data[k]??'—')}</td><td className="p-2">{String(v)}</td></tr>)}</tbody></table></div>}
    {item.state==='approved' && <p className="text-sm">{item.data.applied==='yes'?'Approved changes applied.':'Approved; application is incomplete. The original actor must resume the operation from Projects.'}</p>}
    {!action && <div className="flex flex-wrap gap-2">{item.actions.map(a=><Button key={a} variant="primary" onClick={()=>setAction(a)}>{transitionLabel(configured,a)}</Button>)}{!item.actions.length && <p className="text-sm text-muted-foreground">No action is available to you at this stage.</p>}</div>}
    {action && <ProjectAction key={`${item.id}:${action}`} item={item} action={action} done={()=>setAction(null)} />}
    {item.kind==='HRMS.Project' && <><h3 className="font-semibold">Team and allocations</h3>{board?.allocations.filter(a=>a.data.project_id===item.id).map(a=><p key={a.id} className="text-sm"><Link className="text-blue-700 underline" to={`/hrms/workflows?case=${a.id}`}>{val(a.data,'employee_name')} · {val(a.data,'project_role_name')} · {val(a.data,'percentage')}% · {label(a.state)}</Link></p>)}<h3 className="font-semibold">Approval history</h3>{board?.requests.filter(r=>r.data.project_id===item.id).map(r=><p key={r.id} className="text-sm"><Link className="text-blue-700 underline" to={`/hrms/workflows?case=${r.id}`}>{r.kind==='HRMS.ProjectChange'?'Project':'Allocation'} · {label(val(r.data,'kind'))} · {label(r.state)} · Approver: {val(r.data,'approver_name')}</Link></p>)}</>}
  </section>;
}
