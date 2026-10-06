import { createRequestId } from '../requestId';
import { FileCheck2, FileText, BookOpen, CalendarDays, BriefcaseBusiness, Users, Plus, ArrowUpRight } from 'lucide-react';
import { WorkPanel } from '../components/WorkPanel';
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { WorkFromHome } from './WorkFromHome';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { request, getApiErrorMessage } from '@/core/services/api/client';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { useHrmsCapabilities } from '../capabilities';
import { WorkflowStages } from '../workflows/WorkflowConfiguration';
import { PageHero } from '../components/PageHero';
export const CONTENT_TYPES=['HRMS.Policy','HRMS.LearningEvent','HRMS.HolidayCalendar','HRMS.JobDescription','HRMS.JobOpening'];
export const CONTENT_LABELS=['Policies','L&D calendar','Holidays','Job descriptions','Open positions'];
const internal=new Set(['author_id','author_name','approver_name','publication_id','published_at','revision','hrms_operation_key','identifier']);
type Data=Record<string,string|number>;
type Item={entity_id:string;kind:string;state:string;state_label:string;data:Data;actions:string[];workflow_configuration:{transitions:{trigger:string;label:string;from_state:string}[]}};
type Board={items:Item[];creatable:string[];approvers:{id:string;name:string}[];people:{id:string;name:string}[]};
type Field={field:string;type:string;description?:string;required?:boolean;read_only?:boolean;placeholder?:string;enum_values?:string[];enum_labels?:Record<string,string>;col_span?:number};
const label=(s:string)=>s.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());
const input='hrms-field-input';
const contentIcons=[FileText,BookOpen,CalendarDays,BriefcaseBusiness,Users];
const contentNames=['policy','learning event','holiday calendar','job description','open position'];

export function useCockpitBoard() {
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
 return <WorkPanel title="HR content" description="Review approvals and prepare publications." icon={FileCheck2} count={items.length} loading={query.isLoading} error={query.isError ? getApiErrorMessage(query.error) : undefined} retry={() => void query.refetch()} empty="No content approvals or publications are waiting for you.">
  <ul className="space-y-3">{items.map(item => <li key={item.entity_id} className="hrms-work-item">
   <h3 className="font-semibold">{item.data.title}</h3>
   <p className="mt-1 text-sm text-muted-foreground">{CONTENT_LABELS[CONTENT_TYPES.indexOf(item.kind)]} · {item.state_label} · Submitted by {item.data.author_name || 'HR'}</p>
   <Button className="hrms-outline-button mt-3" variant="outline" onClick={() => setSelected(item.entity_id)}>
    {item.actions.includes('approve') ? 'Review approval' : 'Review for publication'}
   </Button>
  </li>)}</ul>
  <Sheet open={selected !== null} onOpenChange={open => { if (!open) setSelected(null); }}>
   <SheetContent className="hrms-brand hrms-review-drawer overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-4xl">
    <SheetHeader><SheetTitle>Review HR content</SheetTitle></SheetHeader>
    {selected && <CockpitPage key={selected} entityId={selected} />}
   </SheetContent>
  </Sheet>
 </WorkPanel>;
}

export function ContentCard({item}:{item:Record<string,unknown>}) {
 return <article className="hrms-surface hrms-content-preview"><h3 className="hrms-case-name">{String(item.title??'')}</h3>{['location','effective_date','event_date','end_date','trainer','year','department','skills','openings','work_mode','application_deadline'].filter(k=>item[k]).map(k=><p key={k} className="text-sm"><strong>{label(k)}: </strong>{String(item[k])}</p>)}<p className="whitespace-pre-wrap">{String(item.body??'')}</p>{Boolean(item.holidays)&&<pre className="whitespace-pre-wrap font-sans text-sm">{String(item.holidays)}</pre>}{typeof item.public_url==='string'&&item.public_url.startsWith('https://')&&<a className="hrms-text-link" href={item.public_url} target="_blank" rel="noopener noreferrer">Open document / registration / application</a>}</article>;
}
function Editor({kind,item,board,done}:{kind:string;item?:Item;board:Board;done:()=>void}) {
 const [data,setData]=useState<Data>(()=>item?Object.fromEntries(Object.entries(item.data).filter(([k])=>!internal.has(k))):{audience:'employees'});
 const [key,setKey]=useState(()=>createRequestId());
 const [submitted,setSubmitted]=useState<Data|null>(null);
 const client=useQueryClient();
 const schema=useQuery({queryKey:['hrms','form-config',kind],queryFn:()=>request<{fields:Field[]}>(`/hrms/forms/${kind}`),staleTime:0});
 const save=useMutation({mutationFn:()=>request(item?`/hrms/cockpit/${item.entity_id}/actions`:'/hrms/cockpit/actions',{method:'POST',body:JSON.stringify({action:item?'edit':'create',entity_type:kind,data:submitted??data,expected_revision:item?.data.revision??0,idempotency_key:key})}),onSuccess:async()=>{await client.invalidateQueries({queryKey:['hrms']});done();}});
 if(schema.isLoading)return <p>Loading configured form…</p>;
 if(schema.isError)return <p role="alert">{getApiErrorMessage(schema.error)}</p>;
 return <form className="hrms-surface hrms-people-form hrms-content-editor" onSubmit={e=>{e.preventDefault();setSubmitted(data);save.mutate();}}><h2 className="hrms-section-heading">{item?'Edit draft':'Create content'}</h2><fieldset disabled={save.isPending||submitted!==null} className="grid gap-4 sm:grid-cols-2">{schema.data?.fields.filter(f=>!internal.has(f.field)).map(f=>{
 const choices=f.field==='approver_id'?board.approvers:f.field==='hiring_manager_id'?board.people:f.field==='job_description_id'?board.items.filter(r=>r.kind==='HRMS.JobDescription'&&r.state==='published').map(r=>({id:r.entity_id,name:String(r.data.title)})):undefined;
 const props={className:input,required:f.required,disabled:f.read_only,value:data[f.field]??'',onChange:(e:React.ChangeEvent<HTMLInputElement|HTMLTextAreaElement|HTMLSelectElement>)=>setData({...data,[f.field]:f.type==='integer'&&e.target.value!==''?Number(e.target.value):e.target.value}),placeholder:f.placeholder};
 return <label key={f.field} className={`space-y-1 text-sm ${f.col_span===2||f.type==='text'?'sm:col-span-2':''}`}><span>{f.description||label(f.field)}</span>{choices?<select {...props}><option value="">Select…</option>{choices.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select>:f.enum_values?.length?<select {...props}><option value="">Select…</option>{f.enum_values.map(v=><option key={v} value={v}>{f.enum_labels?.[v]??label(v)}</option>)}</select>:f.type==='text'?<textarea {...props} rows={f.field==='body'?6:4}/>:<input {...props} type={f.type==='date'?'date':f.type==='integer'?'number':'text'}/>}</label>;
 })}</fieldset>{!board.approvers.length&&<p role="alert">An independent active approver is required. Configure cockpit approvers under Settings → Roles.</p>}{save.isError&&<p role="alert" className="text-destructive">{getApiErrorMessage(save.error)}. Retry keeps the same request.</p>}<div className="hrms-form-actions">{save.isError && (save.error as {status?:number}).status===422 && <Button className="hrms-outline-button" type="button" variant="outline" onClick={()=>{setSubmitted(null);setKey(createRequestId());save.reset();}}>Correct draft</Button>}<Button className="hrms-primary-button" variant="primary" disabled={save.isPending||!board.approvers.length} type="submit">{save.isError?'Retry save':'Save draft'}</Button><Button className="hrms-outline-button" type="button" variant="outline" disabled={save.isPending} onClick={done}>Cancel</Button></div><p className="text-sm text-muted-foreground">Public content and linked documents will be visible without signing in. Save as a draft, preview, then submit for independent approval.</p></form>;
}
export default function CockpitPage({entityId}:{entityId?:string}) {
 const [params,setParams]=useSearchParams();
 const caps=useHrmsCapabilities();
 const wfh=params.get('area')==='wfh';
 if(entityId)return <ContentCockpit entityId={entityId}/>;
 return <><nav className="hrms-content-categories px-6 pt-6" aria-label="HR Cockpit areas"><button aria-pressed={!wfh} onClick={()=>setParams({})}>Content & publishing</button>{caps.data?.capabilities.includes('wfh:approve')&&<button aria-pressed={wfh} onClick={()=>setParams({area:'wfh'})}>Work from home</button>}</nav>{wfh&&caps.data?.capabilities.includes('wfh:approve')?<main className="hrms-workspace-page"><WorkFromHome cockpit/></main>:<ContentCockpit/>}</>;
}

function ContentCockpit({entityId}:{entityId?:string}) {
 const caps=useHrmsCapabilities();const client=useQueryClient();const [kind,setKind]=useState(CONTENT_TYPES[0]);const [creating,setCreating]=useState(false);const [selected,setSelected]=useState<string|null>(entityId??null);const [editing,setEditing]=useState(false);const [pending,setPending]=useState<{id:string;action:string;revision:number;key:string}|null>(null);
 const [publishedOnly,setPublishedOnly]=useState(false);
 const query=useCockpitBoard();
 const act=useMutation({mutationFn:(p:NonNullable<typeof pending>)=>request<{entity_id:string}>(`/hrms/cockpit/${p.id}/actions`,{method:'POST',body:JSON.stringify({action:p.action,expected_revision:p.revision,idempotency_key:p.key})}),onSuccess:async(result)=>{setSelected(result.entity_id);setPending(null);await client.invalidateQueries({queryKey:['hrms']});}});
 if(caps.isLoading)return <p className="p-6">Loading access…</p>;
 if(!caps.data?.capabilities.includes('cockpit:view'))return <p className="p-6">HR Cockpit is not available to your role.</p>;
 const board=query.data;const item=board?.items.find(r=>r.entity_id===(entityId??selected));
 const categoryIndex=CONTENT_TYPES.indexOf(kind);
 const CategoryIcon=contentIcons[categoryIndex];
 const rows=board?.items.filter(r=>r.kind===kind&&(!publishedOnly||r.state==='published'))??[];
 return <main className={`hrms-brand ${entityId?'hrms-cockpit-embedded':'hrms-workspace-page'} hrms-cockpit-page`}>
  {!entityId&&<PageHero eyebrow="Keep people connected" title="HR Cockpit" intro="Share knowledge, opportunities, and what’s coming next." illustration="cockpit"
    actions={<Link className="hrms-outline-button" to="/hrms/content">Published information <ArrowUpRight size={16}/></Link>}
    stats={board ? [
      { label: 'Drafts', value: board.items.filter(r => r.state === 'draft').length },
      { label: 'Pending approval', value: board.items.filter(r => r.state === 'pending_approval').length, tone: 'attention' },
      { label: 'Published', value: board.items.filter(r => r.state === 'published').length, tone: 'positive' },
      { label: 'Needs your action', value: board.items.filter(r => r.actions.includes('approve') || r.actions.includes('publish')).length },
    ] : undefined} />}
  {query.isLoading&&<p role="status" className="hrms-work-feedback">Loading content…</p>}
  {query.isError&&<div role="alert" className="hrms-notice hrms-notice--error"><p>{getApiErrorMessage(query.error)}</p><button className="hrms-outline-button" onClick={()=>void query.refetch()}>Try again</button></div>}
  {!entityId&&<nav className="hrms-content-categories" aria-label="Content categories">{CONTENT_TYPES.map((t,i)=>{const Icon=contentIcons[i];return <button key={t} type="button" aria-pressed={kind===t} onClick={()=>{setKind(t);setSelected(null);setCreating(false);setEditing(false);}}><Icon size={20} strokeWidth={1.25} aria-hidden="true"/>{CONTENT_LABELS[i]}</button>;})}</nav>}
  {board&&!entityId&&!item&&<>
   <nav className="hrms-content-categories" aria-label="Publication status"><button type="button" aria-pressed={!publishedOnly} onClick={()=>setPublishedOnly(false)}>All content</button><button type="button" aria-pressed={publishedOnly} onClick={()=>setPublishedOnly(true)}><FileCheck2 size={18}/>Published items</button></nav>
   <section className="hrms-surface hrms-content-directory">
    <div className="hrms-directory-heading"><span className="hrms-work-icon"><CategoryIcon size={23} strokeWidth={1.25}/></span><div><h2>{CONTENT_LABELS[categoryIndex]}</h2><p>{rows.length} {rows.length===1?'item':'items'} · {publishedOnly?'Currently published':'Draft, approve, and publish'}</p></div>{board.creatable.includes(kind)&&<button type="button" className="hrms-primary-button" onClick={()=>setCreating(true)}><Plus size={16}/>Add {contentNames[categoryIndex]}</button>}</div>
    <div className="hrms-table-scroll"><table className="hrms-people-table"><thead><tr>{['Title','Status','Audience','Approver','Actions'].map(x=><th key={x}>{x}</th>)}</tr></thead><tbody>{rows.map(r=><tr key={r.entity_id}><td><button className="hrms-text-link" onClick={()=>setSelected(r.entity_id)}>{r.data.title}</button></td><td><span className="hrms-status" data-state={r.state}>{r.state_label}</span></td><td className="capitalize">{r.data.audience}</td><td>{r.data.approver_name||'—'}</td><td><button className="hrms-outline-button" onClick={()=>setSelected(r.entity_id)}>View details</button></td></tr>)}{!rows.length&&<tr><td colSpan={5}><div className="hrms-work-empty"><CategoryIcon size={28} strokeWidth={1.25}/><h3>No {publishedOnly?'published ':''}{CONTENT_LABELS[categoryIndex].toLowerCase()} yet</h3><p>{publishedOnly?'Published content will appear here with its audience and approver.':board.creatable.includes(kind)?'Create a draft to get started.':'Content shared with your role will appear here.'}</p></div></td></tr>}</tbody></table></div>
   </section>
   <Sheet open={creating} onOpenChange={setCreating}><SheetContent className="hrms-brand hrms-review-drawer overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-4xl"><SheetHeader><SheetTitle>Add {contentNames[categoryIndex]}</SheetTitle></SheetHeader><div className="p-6">{creating&&<Editor key={kind} kind={kind} board={board} done={()=>setCreating(false)}/>}</div></SheetContent></Sheet>
  </>}
  {item&&board&&<section className="hrms-content-detail">
   {!entityId&&<button className="hrms-outline-button hrms-content-back" onClick={()=>{setSelected(null);setEditing(false);}}>Back to content</button>}
   <div className="hrms-surface hrms-content-summary"><h2 className="hrms-case-name">{item.data.title}</h2><div className="hrms-heading-actions"><span className="hrms-status" data-state={item.state}>{item.state_label}</span><span className="hrms-muted">Audience: {item.data.audience} · Approver: {item.data.approver_name||'—'}</span></div></div>
   <WorkflowStages entityId={item.entity_id}/><h2 className="hrms-section-heading">Publication preview</h2><ContentCard item={item.data}/>
   {editing?<Editor key={item.entity_id} kind={item.kind} item={item} board={board} done={()=>setEditing(false)}/>:<div className="hrms-heading-actions">{item.actions.map(a=><button type="button" className="hrms-primary-button" key={a} disabled={act.isPending||pending!==null} onClick={()=>{if(a==='edit'){setEditing(true);return;}const p={id:item.entity_id,action:a,revision:Number(item.data.revision??0),key:createRequestId()};setPending(p);act.mutate(p);}}>{item.workflow_configuration.transitions.find(t=>t.trigger===a&&t.from_state===item.state)?.label??label(a)}</button>)}</div>}
   {act.isError&&<div role="alert" className="hrms-notice hrms-notice--error"><p>{getApiErrorMessage(act.error)}</p>{pending&&<button className="hrms-outline-button" onClick={()=>act.mutate(pending)}>Retry action</button>}</div>}
   <Link className="hrms-text-link" to={`/hrms/workflows?case=${item.entity_id}`}>View in Workflows <ArrowUpRight size={15}/></Link>
  </section>}
 </main>;
}
