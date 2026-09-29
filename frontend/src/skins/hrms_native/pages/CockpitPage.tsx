import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { request, getApiErrorMessage } from '@/core/services/api/client';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { useHrmsCapabilities } from '../capabilities';
import { WorkflowStages } from '../workflows/WorkflowConfiguration';
export const CONTENT_TYPES=['HRMS.Policy','HRMS.LearningEvent','HRMS.HolidayCalendar','HRMS.JobDescription','HRMS.JobOpening'];
export const CONTENT_LABELS=['Policies','L&D calendar','Holidays','Job descriptions','Open positions'];
const internal=new Set(['author_id','author_name','approver_name','publication_id','published_at','revision','hrms_operation_key','identifier']);
type Data=Record<string,string|number>;
type Item={entity_id:string;kind:string;state:string;state_label:string;data:Data;actions:string[];workflow_configuration:{transitions:{trigger:string;label:string;from_state:string}[]}};
type Board={items:Item[];creatable:string[];approvers:{id:string;name:string}[];people:{id:string;name:string}[]};
type Field={field:string;type:string;description?:string;required?:boolean;read_only?:boolean;placeholder?:string;enum_values?:string[];enum_labels?:Record<string,string>;col_span?:number};
const label=(s:string)=>s.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());
const input='w-full rounded-lg border bg-background p-2';

function useCockpitBoard() {
 const caps = useHrmsCapabilities();
 return useQuery({
  queryKey: ['hrms', 'cockpit'],
  queryFn: () => request<Board>('/hrms/cockpit'),
  enabled: caps.data?.capabilities.includes('cockpit:view') ?? false,
 });
}

/** Reuse server-authorized actions and the cockpit detail view in My Work. */
export function CockpitInbox() {
 const caps = useHrmsCapabilities();
 const query = useCockpitBoard();
 const [selected, setSelected] = useState<string | null>(null);
 const items = query.data?.items.filter(item =>
  item.actions.includes('approve') || item.actions.includes('publish')) ?? [];
 if (!caps.data?.capabilities.includes('cockpit:view')) return null;
 return <section className="space-y-3" aria-labelledby="cockpit-inbox-title">
  <h2 id="cockpit-inbox-title" className="font-semibold">HR content approvals and publishing</h2>
  {query.isLoading && <p role="status">Loading content actions…</p>}
  {query.isError && <p role="alert">{getApiErrorMessage(query.error)}</p>}
  {query.data && items.length === 0 && <p className="text-sm text-muted-foreground">No content approvals or publications are waiting for you.</p>}
  <ul className="space-y-3">{items.map(item => <li key={item.entity_id} className="rounded-xl border bg-background p-4">
   <h3 className="font-semibold">{item.data.title}</h3>
   <p className="mt-1 text-sm text-muted-foreground">{CONTENT_LABELS[CONTENT_TYPES.indexOf(item.kind)]} · {item.state_label} · Submitted by {item.data.author_name || 'HR'}</p>
   <Button className="mt-3" variant="outline" onClick={() => setSelected(item.entity_id)}>
    {item.actions.includes('approve') ? 'Review approval' : 'Review for publication'}
   </Button>
  </li>)}</ul>
  <Sheet open={selected !== null} onOpenChange={open => { if (!open) setSelected(null); }}>
   <SheetContent className="overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-4xl">
    <SheetHeader><SheetTitle>Review HR content</SheetTitle></SheetHeader>
    {selected && <CockpitPage key={selected} entityId={selected} />}
   </SheetContent>
  </Sheet>
 </section>;
}

export function ContentCard({item}:{item:Record<string,unknown>}) {
 return <article className="space-y-3 rounded-xl border bg-white p-5"><h3 className="text-xl font-semibold">{String(item.title??'')}</h3>{['location','effective_date','event_date','end_date','trainer','year','department','skills','openings','work_mode','application_deadline'].filter(k=>item[k]).map(k=><p key={k} className="text-sm"><strong>{label(k)}: </strong>{String(item[k])}</p>)}<p className="whitespace-pre-wrap">{String(item.body??'')}</p>{Boolean(item.holidays)&&<pre className="whitespace-pre-wrap font-sans text-sm">{String(item.holidays)}</pre>}{typeof item.public_url==='string'&&item.public_url.startsWith('https://')&&<a className="text-blue-700 underline" href={item.public_url} target="_blank" rel="noopener noreferrer">Open document / registration / application</a>}</article>;
}
function Editor({kind,item,board,done}:{kind:string;item?:Item;board:Board;done:()=>void}) {
 const [data,setData]=useState<Data>(()=>item?Object.fromEntries(Object.entries(item.data).filter(([k])=>!internal.has(k))):{audience:'employees'});
 const [key,setKey]=useState(()=>crypto.randomUUID());
 const [submitted,setSubmitted]=useState<Data|null>(null);
 const client=useQueryClient();
 const schema=useQuery({queryKey:['hrms','form-config',kind],queryFn:()=>request<{fields:Field[]}>(`/hrms/forms/${kind}`),staleTime:0});
 const save=useMutation({mutationFn:()=>request(item?`/hrms/cockpit/${item.entity_id}/actions`:'/hrms/cockpit/actions',{method:'POST',body:JSON.stringify({action:item?'edit':'create',entity_type:kind,data:submitted??data,expected_revision:item?.data.revision??0,idempotency_key:key})}),onSuccess:async()=>{await client.invalidateQueries({queryKey:['hrms']});done();}});
 if(schema.isLoading)return <p>Loading configured form…</p>;
 if(schema.isError)return <p role="alert">{getApiErrorMessage(schema.error)}</p>;
 return <form className="space-y-4 rounded-xl border p-5" onSubmit={e=>{e.preventDefault();setSubmitted(data);save.mutate();}}><h2 className="text-lg font-semibold">{item?'Edit draft':'Create content'}</h2><fieldset disabled={save.isPending||submitted!==null} className="grid gap-4 sm:grid-cols-2">{schema.data?.fields.filter(f=>!internal.has(f.field)).map(f=>{
 const choices=f.field==='approver_id'?board.approvers:f.field==='hiring_manager_id'?board.people:f.field==='job_description_id'?board.items.filter(r=>r.kind==='HRMS.JobDescription'&&r.state==='published').map(r=>({id:r.entity_id,name:String(r.data.title)})):undefined;
 const props={className:input,required:f.required,disabled:f.read_only,value:data[f.field]??'',onChange:(e:React.ChangeEvent<HTMLInputElement|HTMLTextAreaElement|HTMLSelectElement>)=>setData({...data,[f.field]:f.type==='integer'&&e.target.value!==''?Number(e.target.value):e.target.value}),placeholder:f.placeholder};
 return <label key={f.field} className={`space-y-1 text-sm ${f.col_span===2||f.type==='text'?'sm:col-span-2':''}`}><span>{f.description||label(f.field)}</span>{choices?<select {...props}><option value="">Select…</option>{choices.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select>:f.enum_values?.length?<select {...props}><option value="">Select…</option>{f.enum_values.map(v=><option key={v} value={v}>{f.enum_labels?.[v]??label(v)}</option>)}</select>:f.type==='text'?<textarea {...props} rows={f.field==='body'?6:4}/>:<input {...props} type={f.type==='date'?'date':f.type==='integer'?'number':'text'}/>}</label>;
 })}</fieldset>{!board.approvers.length&&<p role="alert">An independent active approver is required. Configure cockpit approvers under Settings → Roles.</p>}{save.isError&&<p role="alert" className="text-destructive">{getApiErrorMessage(save.error)}. Retry keeps the same request.</p>}<div className="flex gap-2">{save.isError && (save.error as {status?:number}).status===422 && <Button type="button" variant="outline" onClick={()=>{setSubmitted(null);setKey(crypto.randomUUID());save.reset();}}>Correct draft</Button>}<Button variant="primary" disabled={save.isPending||!board.approvers.length} type="submit">{save.isError?'Retry save':'Save draft'}</Button><Button type="button" variant="outline" disabled={save.isPending} onClick={done}>Cancel</Button></div><p className="text-sm text-muted-foreground">Public content and linked documents will be visible without signing in. Save as a draft, preview, then submit for independent approval.</p></form>;
}
export default function CockpitPage({entityId}:{entityId?:string}) {
 const caps=useHrmsCapabilities();const client=useQueryClient();const [kind,setKind]=useState(CONTENT_TYPES[0]);const [creating,setCreating]=useState(false);const [selected,setSelected]=useState<string|null>(entityId??null);const [editing,setEditing]=useState(false);const [pending,setPending]=useState<{id:string;action:string;revision:number;key:string}|null>(null);
 const query=useCockpitBoard();
 const act=useMutation({mutationFn:(p:NonNullable<typeof pending>)=>request<{entity_id:string}>(`/hrms/cockpit/${p.id}/actions`,{method:'POST',body:JSON.stringify({action:p.action,expected_revision:p.revision,idempotency_key:p.key})}),onSuccess:async(result)=>{setSelected(result.entity_id);setPending(null);await client.invalidateQueries({queryKey:['hrms']});}});
 if(caps.isLoading)return <p className="p-6">Loading access…</p>;
 if(!caps.data?.capabilities.includes('cockpit:view'))return <p className="p-6">HR Cockpit is not available to your role.</p>;
 const board=query.data;const item=board?.items.find(r=>r.entity_id===(entityId??selected));
 return <main className="space-y-5 p-6"><h1 className="text-2xl font-semibold">HR Cockpit</h1><p>Draft, approve and publish employee and public information.</p><Link className="text-blue-700 underline" to="/hrms/content">View published information</Link>{query.isLoading&&<p>Loading content…</p>}{query.isError&&<p role="alert">{getApiErrorMessage(query.error)}</p>}{!entityId&&<nav className="flex flex-wrap gap-2">{CONTENT_TYPES.map((t,i)=><Button key={t} variant={kind===t?'primary':'outline'} onClick={()=>{setKind(t);setSelected(null);setCreating(false);setEditing(false);}}>{CONTENT_LABELS[i]}</Button>)}</nav>}
 {board&&!entityId&&!item&&<><Button disabled={!board.creatable.includes(kind)} variant="primary" onClick={()=>setCreating(true)}>Add {CONTENT_LABELS[CONTENT_TYPES.indexOf(kind)].toLowerCase()}</Button>{creating&&<Editor key={kind} kind={kind} board={board} done={()=>setCreating(false)}/>}<div className="overflow-auto rounded-xl border"><table className="w-full text-left text-sm"><thead><tr>{['Title','Status','Audience','Approver','Actions'].map(x=><th className="p-3" key={x}>{x}</th>)}</tr></thead><tbody>{board.items.filter(r=>r.kind===kind).map(r=><tr className="border-t" key={r.entity_id}><td className="p-3">{r.data.title}</td><td>{r.state_label}</td><td>{r.data.audience}</td><td>{r.data.approver_name}</td><td><Button variant="outline" onClick={()=>setSelected(r.entity_id)}>View details</Button></td></tr>)}{!board.items.some(r=>r.kind===kind)&&<tr><td colSpan={5} className="p-6">No content yet. Create the first draft.</td></tr>}</tbody></table></div></>}
 {item&&board&&<section className="space-y-4">{!entityId&&<Button variant="outline" onClick={()=>{setSelected(null);setEditing(false);}}>Back to content</Button>}<p>{item.state_label} · {item.data.audience} · Approver: {item.data.approver_name}</p><WorkflowStages entityId={item.entity_id}/><h2 className="font-semibold">Publication preview</h2><ContentCard item={item.data}/>{editing?<Editor key={item.entity_id} kind={item.kind} item={item} board={board} done={()=>setEditing(false)}/>:<div className="flex flex-wrap gap-2">{item.actions.map(a=><Button key={a} variant="primary" disabled={act.isPending||pending!==null} onClick={()=>{if(a==='edit'){setEditing(true);return;}const p={id:item.entity_id,action:a,revision:Number(item.data.revision??0),key:crypto.randomUUID()};setPending(p);act.mutate(p);}}>{item.workflow_configuration.transitions.find(t=>t.trigger===a&&t.from_state===item.state)?.label??label(a)}</Button>)}</div>}{act.isError&&<div role="alert"><p>{getApiErrorMessage(act.error)}</p>{pending&&<Button onClick={()=>act.mutate(pending)}>Retry action</Button>}</div>}<Link className="text-blue-700 underline" to={`/hrms/workflows?case=${item.entity_id}`}>View in Workflows</Link></section>}
 </main>;
}
