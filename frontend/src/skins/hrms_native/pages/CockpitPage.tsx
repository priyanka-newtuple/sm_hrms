import OffboardingPage from './OffboardingPage';
import CreateOffer from './CreateOffer';
import { RecordTabs } from '../components/record/RecordTabs';
import { OnboardingTracker } from './OnboardingTracker';
import AddEmployee from './AddEmployee';
import { ConfiguredInputs, ConfiguredForm, useFormSchema, formValues } from '../forms/ConfiguredForm';
import { createRequestId } from '../requestId';
import { FileText, BookOpen, CalendarDays, BriefcaseBusiness, Users, Plus, ArrowUpRight, ChevronRight } from 'lucide-react';
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { request, getApiErrorMessage } from '@/core/services/api/client';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { useHrmsCapabilities } from '../capabilities';
import { WorkflowStages } from '../workflows/WorkflowConfiguration';
import { AddedSteps } from '../workflows/AddedSteps';
import { PageHero } from '../components/PageHero';
import { FilterSelect, ListEmpty, Pager, SearchField, Segmented, Toolbar } from '../components/ListKit';
import { matchesText, usePaged } from '../components/useList';
import { formatDate, toDate } from '../public-info/format';
export const CONTENT_TYPES=['HRMS.Policy','HRMS.LearningEvent','HRMS.HolidayCalendar','HRMS.JobDescription','HRMS.JobOpening'];
export const CONTENT_LABELS=['Policies','L&D calendar','Holidays','Job descriptions','Open positions'];
const internal=new Set(['author_id','author_name','approver_name','publication_id','published_at','revision','hrms_operation_key','identifier']);
type Data=Record<string,string|number>;
type Item={entity_id:string;kind:string;state:string;state_label:string;data:Data;actions:string[];superseded?:boolean;expired?:boolean;workflow_configuration:{transitions:{trigger:string;label:string;from_state:string}[]}};
/** Replaced by a later published revision, or past its end date: shown, but not live. */
const notLive=(r:Item)=>Boolean(r.superseded||r.expired);
const statusText=(r:Item)=>r.superseded?'Replaced by a newer version':r.expired?'Expired':r.state_label;
type Board={items:Item[];creatable:string[];approvers:{id:string;name:string}[];people:{id:string;name:string}[]};

const label=(s:string)=>s.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());
const contentIcons=[FileText,BookOpen,CalendarDays,BriefcaseBusiness,Users];
const contentNames=['policy','learning event','holiday calendar','job description','open position'];
const contentSlugs=['policies','learning','holidays','job-descriptions','openings'];

/** Status filters for the content list; "Active" hides archived items and replaced revisions. */
const STATUS_FILTERS:{value:string;label:string;test:(r:Item)=>boolean}[]=[
 {value:'active',label:'Active',test:r=>r.state!=='archived'&&!r.superseded},
 {value:'action',label:'Needs your action',test:r=>r.actions.includes('approve')||r.actions.includes('publish')},
 {value:'draft',label:'Drafts',test:r=>r.state==='draft'},
 {value:'pending_approval',label:'Pending approval',test:r=>r.state==='pending_approval'},
 {value:'approved',label:'Approved',test:r=>r.state==='approved'},
 {value:'live',label:'Published',test:r=>r.state==='published'&&!notLive(r)},
 {value:'inactive',label:'Paused, closed or expired',test:r=>r.state!=='archived'&&!r.superseded&&(r.state==='paused'||r.state==='closed'||Boolean(r.expired))},
 {value:'history',label:'Archived or replaced',test:r=>r.state==='archived'||Boolean(r.superseded)},
 {value:'all',label:'All',test:()=>true},
];
const AUDIENCES=[{value:'all',label:'All'},{value:'employees',label:'Employees'},{value:'public',label:'Public'}];
/** Work in progress first, then live content, then the rest; alphabetical within each group. */
const STATE_ORDER=['pending_approval','approved','draft','published','paused','closed','archived'];
const rank=(r:Item)=>(notLive(r)?10:0)+(STATE_ORDER.indexOf(r.state)+1||STATE_ORDER.length);
const day=(v:unknown)=>{const d=toDate(v);return d?formatDate(d):'';};
/** The one detail that tells similar items apart in the list. */
function detail(r:Item){
 const d=r.data;
 switch(r.kind){
  case 'HRMS.Policy':return d.effective_date?`Effective ${day(d.effective_date)}`:'';
  case 'HRMS.LearningEvent':return [day(d.event_date),d.trainer,d.location].filter(Boolean).join(' · ');
  case 'HRMS.HolidayCalendar':return [d.year,d.location].filter(Boolean).join(' · ');
  case 'HRMS.JobDescription':return String(d.department??'');
  case 'HRMS.JobOpening':return [d.location,d.work_mode,d.application_deadline&&`Apply by ${day(d.application_deadline)}`].filter(Boolean).join(' · ');
  default:return '';
 }
}

export function useCockpitBoard() {
 const caps = useHrmsCapabilities();
 return useQuery({
  queryKey: ['hrms', 'cockpit'],
  queryFn: () => request<Board>('/hrms/cockpit'),
  enabled: caps.data?.capabilities.includes('cockpit:view') ?? false,
 });
}


export function ContentCard({item}:{item:Record<string,unknown>}) {
 return <article className="hrms-surface hrms-content-preview"><h3 className="hrms-case-name">{String(item.title??'')}</h3>{['location','effective_date','event_date','end_date','trainer','year','department','skills','openings','work_mode','application_deadline'].filter(k=>item[k]).map(k=><p key={k} className="text-sm"><strong>{label(k)}: </strong>{String(item[k])}</p>)}<p className="whitespace-pre-wrap">{String(item.body??'')}</p>{Boolean(item.holidays)&&<pre className="whitespace-pre-wrap font-sans text-sm">{String(item.holidays)}</pre>}{typeof item.public_url==='string'&&item.public_url.startsWith('https://')&&<a className="hrms-text-link" href={item.public_url} target="_blank" rel="noopener noreferrer">Open document / registration / application</a>}</article>;
}
function Editor({kind,item,board,done}:{kind:string;item?:Item;board:Board;done:()=>void}) {
 const [data,setData]=useState<Data>(()=>item?Object.fromEntries(Object.entries(item.data).filter(([k])=>!internal.has(k))):{audience:'employees'});
 const [key,setKey]=useState(()=>createRequestId());
 const [submitted,setSubmitted]=useState<Data|null>(null);
 const client=useQueryClient();
 const schema=useFormSchema(kind);
 const values=()=>formValues(schema.data?.fields??[],data,[...internal]);
 const save=useMutation({mutationFn:()=>request(item?`/hrms/cockpit/${item.entity_id}/actions`:'/hrms/cockpit/actions',{method:'POST',body:JSON.stringify({action:item?'edit':'create',entity_type:kind,data:submitted??values(),expected_revision:item?.data.revision??0,idempotency_key:key})}),onSuccess:async()=>{await client.invalidateQueries({queryKey:['hrms']});done();}});
 if(schema.isLoading)return <p>Loading configured form…</p>;
 if(schema.isError)return <p role="alert">{getApiErrorMessage(schema.error)}</p>;
 return <ConfiguredForm entityType={kind}><form className="hrms-surface hrms-people-form hrms-content-editor" onSubmit={e=>{e.preventDefault();setSubmitted(values() as Data);save.mutate();}}><h2 className="hrms-section-heading">{item?'Edit draft':'Create content'}</h2><fieldset disabled={save.isPending||submitted!==null} className="grid gap-4 sm:grid-cols-2"><ConfiguredInputs values={data} onChange={v=>setData(v as Data)} exclude={[...internal]} adapters={{approver_id:{options:board.approvers},hiring_manager_id:{options:board.people},job_description_id:{options:board.items.filter(r=>r.kind==='HRMS.JobDescription'&&r.state==='published'&&!r.superseded).map(r=>({id:r.entity_id,name:String(r.data.title)}))}}}/></fieldset>{!board.approvers.length&&<p role="alert">An independent active approver is required. Configure cockpit approvers under Settings → Roles.</p>}{save.isError&&<p role="alert" className="text-destructive">{getApiErrorMessage(save.error)}. Retry keeps the same request.</p>}<div className="hrms-form-actions">{save.isError && (save.error as {status?:number}).status===422 && <Button className="hrms-outline-button" type="button" variant="outline" onClick={()=>{setSubmitted(null);setKey(createRequestId());save.reset();}}>Correct draft</Button>}<Button className="hrms-primary-button" variant="primary" disabled={save.isPending||!board.approvers.length} type="submit">{save.isError?'Retry save':'Save draft'}</Button><Button className="hrms-outline-button" type="button" variant="outline" disabled={save.isPending} onClick={done}>Cancel</Button></div><p className="text-sm text-muted-foreground">Public content and linked documents will be visible without signing in. Save as a draft, preview, then submit for independent approval.</p></form></ConfiguredForm>;
}
export default function CockpitPage({entityId}:{entityId?:string}) {
 const [params,setParams]=useSearchParams();
 const caps=useHrmsCapabilities();
 if(entityId)return <ContentCockpit entityId={entityId}/>;
 if(caps.isLoading)return <p role="status">Loading HR access...</p>;
 if(caps.isError)return <p role="alert">Could not load HR access. <button onClick={()=>void caps.refetch()}>Try again</button></p>;
 const allowed=(cap:string)=>caps.data?.capabilities.includes(cap)??false;
 // Work from home lives on its own page; its approvals are on My Tasks.
 const areas=[...(allowed('cockpit:view')?[{id:'offers',label:'Offers'}]:[]),...(allowed('onboarding:view')?[{id:'onboarding',label:'Onboarding'}]:[]),...(allowed('employee:exit')?[{id:'offboarding',label:'Offboarding'}]:[]),...(allowed('cockpit:view')?[{id:'publishing',label:'Content & publishing'}]:[])];
 if(!areas.length)return <p className="p-6">HR Cockpit is not available to your role.</p>;
 const area=areas.find(a=>a.id===params.get('area'))?.id??areas[0].id;
 const tabs=<Segmented variant="underline" label="HR Cockpit areas" value={area} onChange={id=>setParams({area:id})} segments={areas.map(a=>({id:a.id,label:a.label,badge:undefined}))}/>;
 if(area==='publishing')return <ContentCockpit tabs={tabs}/>;
 return <main className="hrms-workspace-page"><PageHero title="HR Cockpit" intro={area==='offers'?'Create offers and follow their approval and acceptance progress.':area==='offboarding'?'Coordinate employee exits, handover and final clearances.':'Coordinate onboarding and help new colleagues settle in.'} illustration="cockpit" tabs={tabs}/>{area==='offers'?<CreateOffer/>:area==='onboarding'?<OnboardingTracker actions={<AddEmployee buttonClassName="hrms-lk-add"/>}/>:<OffboardingPage/>}</main>;
}

function ContentCockpit({entityId,tabs}:{entityId?:string;tabs?:React.ReactNode}) {
 const caps=useHrmsCapabilities();const client=useQueryClient();const [params,setParams]=useSearchParams();const kind=CONTENT_TYPES[Math.max(0,contentSlugs.indexOf(params.get('type')??''))];const [creating,setCreating]=useState(false);const [selected,setSelected]=useState<string|null>(entityId??null);const [editing,setEditing]=useState(false);const [pending,setPending]=useState<{id:string;action:string;revision:number;key:string;data?:Data}|null>(null);const [newApprover,setNewApprover]=useState<string|null>(null);
 const [status,setStatus]=useState('active');const [audience,setAudience]=useState('all');const [search,setSearch]=useState('');
 const query=useCockpitBoard();
 const act=useMutation({mutationFn:(p:NonNullable<typeof pending>)=>request<{entity_id:string}>(`/hrms/cockpit/${p.id}/actions`,{method:'POST',body:JSON.stringify({action:p.action,data:p.data??{},expected_revision:p.revision,idempotency_key:p.key})}),onSuccess:async(result)=>{setSelected(result.entity_id);setPending(null);setNewApprover(null);await client.invalidateQueries({queryKey:['hrms']});}});
 const board=query.data;const item=board?.items.find(r=>r.entity_id===(entityId??selected));
 const categoryIndex=CONTENT_TYPES.indexOf(kind);
 const ofKind=board?.items.filter(r=>r.kind===kind)??[];
 const statusFilter=STATUS_FILTERS.find(f=>f.value===status)??STATUS_FILTERS[0];
 const rows=ofKind.filter(r=>statusFilter.test(r)&&(audience==='all'||r.data.audience===audience)&&matchesText(search,[r.data.title,r.data.approver_name,r.data.author_name,r.data.department,r.data.location,r.data.trainer,r.data.year]))
  .sort((a,b)=>rank(a)-rank(b)||String(a.data.title).localeCompare(String(b.data.title),undefined,{numeric:true,sensitivity:'base'}));
 const paged=usePaged(rows,20,`${kind}|${status}|${audience}|${search}`);
 const filtered=status!=='active'||audience!=='all'||search!=='';
 const chooseKind=(t:string)=>{setParams(p=>{p.set('type',contentSlugs[CONTENT_TYPES.indexOf(t)]);return p;});setSelected(null);setCreating(false);setEditing(false);setSearch('');};
 if(caps.isLoading)return <p className="p-6">Loading access…</p>;
 if(!caps.data?.capabilities.includes('cockpit:view'))return <p className="p-6">HR Cockpit is not available to your role.</p>;
 return <main className={`hrms-brand ${entityId?'hrms-cockpit-embedded':'hrms-workspace-page'} hrms-cockpit-page`}>
  {!entityId&&<PageHero title="HR Cockpit" intro="Share knowledge, opportunities, and what’s coming next." illustration="cockpit" tabs={tabs}
    actions={<Link className="hrms-outline-button" to="/hrms/content">Published information <ArrowUpRight size={16}/></Link>}
    stats={board ? [
      { label: 'Drafts', value: board.items.filter(r => r.state === 'draft').length },
      { label: 'Pending approval', value: board.items.filter(r => r.state === 'pending_approval').length, tone: 'attention' },
      { label: 'Published', value: board.items.filter(r => r.state === 'published' && !notLive(r)).length, tone: 'positive' },
      { label: 'Needs your action', value: board.items.filter(r => r.actions.includes('approve') || r.actions.includes('publish')).length },
    ] : undefined} />}
  {query.isLoading&&<p role="status" className="hrms-work-feedback">Loading content…</p>}
  {query.isError&&<div role="alert" className="hrms-notice hrms-notice--error"><p>{getApiErrorMessage(query.error)}</p><button className="hrms-outline-button" onClick={()=>void query.refetch()}>Try again</button></div>}
  {board&&!entityId&&!item&&<>
   <section className="hrms-lk-card hrms-cockpit-list" aria-label={CONTENT_LABELS[categoryIndex]}>
    <div className="hrms-lk-card-head">
     <Segmented label="Content categories" value={kind} onChange={chooseKind} segments={CONTENT_TYPES.map((t,i)=>({id:t,label:CONTENT_LABELS[i],icon:contentIcons[i],count:board.items.filter(r=>r.kind===t&&r.state!=='archived'&&!r.superseded).length}))}/>
     {board.creatable.includes(kind)&&<button type="button" className="hrms-primary-button hrms-lk-add" onClick={()=>setCreating(true)}><Plus size={16}/>Add {contentNames[categoryIndex]}</button>}
    </div>
    <Toolbar>
     <SearchField value={search} onChange={setSearch} placeholder={`Search ${CONTENT_LABELS[categoryIndex].toLowerCase()}`}/>
     <FilterSelect label="Status" value={status} onChange={setStatus} options={STATUS_FILTERS.map(f=>({value:f.value,label:`${f.label} (${ofKind.filter(f.test).length})`}))}/>
     <FilterSelect label="Audience" value={audience} onChange={setAudience} options={AUDIENCES}/>
     {filtered&&<button type="button" className="hrms-text-link text-sm" onClick={()=>{setStatus('active');setAudience('all');setSearch('');}}>Reset</button>}
    </Toolbar>
    {rows.length?<div className="hrms-lk-scroll"><table className="hrms-lk-table"><thead><tr><th>Title</th><th>Status</th><th>Audience</th><th>Approver</th><th><span className="sr-only">Open</span></th></tr></thead><tbody>{paged.items.map(r=><tr key={r.entity_id} data-row onClick={()=>setSelected(r.entity_id)} className="cursor-pointer">
     <td><button type="button" className="hrms-lk-title" onClick={e=>{e.stopPropagation();setSelected(r.entity_id);}}>{r.data.title}</button>{detail(r)&&<span className="hrms-lk-sub">{detail(r)}</span>}</td>
     <td data-label="Status"><span className="hrms-status" data-state={notLive(r)?'closed':r.state}>{statusText(r)}</span></td>
     <td data-label="Audience" className="capitalize">{r.data.audience}</td>
     <td data-label="Approver">{r.data.approver_name||'—'}</td>
     <td className="hrms-lk-end"><span className="hrms-lk-chevron" aria-hidden="true"><ChevronRight size={16}/></span></td>
    </tr>)}</tbody></table></div>
    :<ListEmpty title={filtered?'Nothing matches these filters':`No ${CONTENT_LABELS[categoryIndex].toLowerCase()} yet`} text={filtered?'Try another status or search, or reset the filters.':board.creatable.includes(kind)?'Create a draft to get started.':'Content shared with your role will appear here.'} action={filtered?<button type="button" onClick={()=>{setStatus('all');setAudience('all');setSearch('');}}>Show everything</button>:undefined}/>}
    <Pager paged={paged} noun={CONTENT_LABELS[categoryIndex].toLowerCase()}/>
   </section>
   <Sheet open={creating} onOpenChange={setCreating}><SheetContent className="hrms-brand hrms-review-drawer overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-4xl"><SheetHeader><SheetTitle>Add {contentNames[categoryIndex]}</SheetTitle></SheetHeader><div className="p-6">{creating&&<Editor key={kind} kind={kind} board={board} done={()=>setCreating(false)}/>}</div></SheetContent></Sheet>
  </>}
  {item&&board&&<section className="hrms-content-detail">
   {!entityId&&<button className="hrms-outline-button hrms-content-back" onClick={()=>{setSelected(null);setEditing(false);}}>Back to content</button>}
   <div className="hrms-surface hrms-content-summary"><h2 className="hrms-case-name">{item.data.title}</h2><div className="hrms-heading-actions"><span className="hrms-status" data-state={notLive(item)?'closed':item.state}>{statusText(item)}</span><span className="hrms-muted">Audience: {item.data.audience} · Approver: {item.data.approver_name||'—'}</span></div></div>
   <RecordTabs key={item.entity_id} entityId={item.entity_id} scope="content">
   <WorkflowStages entityId={item.entity_id}/><h2 className="hrms-section-heading">Publication preview</h2><ContentCard item={item.data}/>
   {editing?<Editor key={item.entity_id} kind={item.kind} item={item} board={board} done={()=>setEditing(false)}/>:<div className="hrms-heading-actions">{item.actions.map(a=><button type="button" className="hrms-primary-button" key={a} disabled={act.isPending||pending!==null} onClick={()=>{if(a==='edit'){setEditing(true);return;}if(a==='change_approver'){setNewApprover('');return;}const p={id:item.entity_id,action:a,revision:Number(item.data.revision??0),key:createRequestId()};setPending(p);act.mutate(p);}}>{item.workflow_configuration.transitions.find(t=>t.trigger===a&&t.from_state===item.state)?.label??label(a)}</button>)}</div>}
   {newApprover!==null&&<form className="hrms-heading-actions" onSubmit={e=>{e.preventDefault();const p={id:item.entity_id,action:'change_approver',revision:Number(item.data.revision??0),key:createRequestId(),data:{approver_id:newApprover}};setPending(p);act.mutate(p);}}>
    <label className="text-sm font-medium">New approver <select required className="hrms-field-input" value={newApprover} onChange={e=>setNewApprover(e.target.value)}><option value="">Select…</option>{board.approvers.filter(a=>a.id!==item.data.approver_id&&a.id!==item.data.author_id).map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
    <button type="submit" className="hrms-primary-button" disabled={!newApprover||act.isPending}>Send to this approver</button><button type="button" className="hrms-outline-button" onClick={()=>setNewApprover(null)}>Cancel</button></form>}
   {item.superseded&&<p className="hrms-notice">A newer revision of this item is published. Pause, close or revise the published version instead.</p>}
   {act.isError&&<div role="alert" className="hrms-notice hrms-notice--error"><p>{getApiErrorMessage(act.error)}</p>{pending&&<button className="hrms-outline-button" onClick={()=>act.mutate(pending)}>Retry action</button>}{pending&&<button className="hrms-outline-button" onClick={()=>{setPending(null);act.reset();}}>Dismiss</button>}</div>}
   {caps.data?.capabilities.includes('cockpit:publish')&&<AddedSteps entityId={item.entity_id}/>}
   <Link className="hrms-text-link" to={`/hrms/workflows?case=${item.entity_id}`}>View in Workflows <ArrowUpRight size={15}/></Link>
  </RecordTabs></section>}
 </main>;
}
