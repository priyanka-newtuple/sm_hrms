import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { request, getApiErrorMessage } from '@/core/services/api/client';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { ConfiguredInputs, type Field } from '../forms/ConfiguredForm';
import { RecordTabs } from '../components/record/RecordTabs';
import { createRequestId } from '../requestId';
import { useHrmsCapabilities } from '../capabilities';

type Row={is_terminal:boolean;entity_id:string;current_state:string;summary_fields:Record<string,string>};
type Detail={entity_id?:string;state?:string;assignee_name?:string;employee_participation?:boolean;values?:Record<string,unknown>;values_hash?:string;editable?:boolean;
  employee?:Record<string,unknown>;fields:Field[];workflow:{id:string;definition:{initial_state:string}};
  actions?:{trigger:string;label?:string;blocked_reasons?:string[]}[]};
const internal=new Set(['notice_verified','departure_verified','withdrawal_verified','clearance_verified','approved_at','departed_at','completed_at','offboarding_employee_user_id']);

export default function OffboardingPage(){
  const caps=useHrmsCapabilities();
  const allowed=caps.data?.capabilities.includes('employee:exit')??false;
  const rows=useQuery({queryKey:['hrms','offboarding'],queryFn:()=>request<Row[]>('/hrms/offboarding'),enabled:allowed});
  const [selected,setSelected]=useState<string|null>(null);
  const [search,setSearch]=useState('');
  const [showClosed,setShowClosed]=useState(false);
  if(!allowed)return <p className="p-6">Offboarding is available to authorized HR administrators.</p>;
  const visible=(rows.data??[]).filter(r=>(showClosed||!r.is_terminal)&&`${r.summary_fields.identifier} ${r.current_state}`.toLowerCase().includes(search.toLowerCase()));
  return <section className="hrms-lk-card">
    <div className="hrms-lk-card-head"><h2 className="hrms-section-heading">Employee offboarding</h2><button className="hrms-primary-button hrms-lk-add" onClick={()=>setSelected('new')}>+ Start offboarding</button></div>
    <div className="p-6"><div className="flex gap-4 mb-5"><input aria-label="Search offboarding" className="hrms-field-input" placeholder="Search employee or stage…" value={search} onChange={e=>setSearch(e.target.value)}/><label className="flex gap-2 items-center"><input type="checkbox" checked={showClosed} onChange={e=>setShowClosed(e.target.checked)}/>Include closed</label></div>
      {rows.isLoading?<p role="status">Loading offboarding…</p>:rows.isError?<p role="alert">{getApiErrorMessage(rows.error)} <button onClick={()=>void rows.refetch()}>Retry</button></p>:!visible.length?<p>No offboarding records in this view.</p>:<ul className="space-y-3">{visible.map(r=><li key={r.entity_id}><button className="hrms-outline-button w-full flex justify-between" onClick={()=>setSelected(r.entity_id)}><span>{r.summary_fields.identifier||r.entity_id}</span><span>{r.current_state}</span></button></li>)}</ul>}
    </div>
    <Sheet open={selected!==null} onOpenChange={open=>{if(!open)setSelected(null);}}><SheetContent className="hrms-brand overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-4xl"><SheetHeader><SheetTitle>Employee offboarding</SheetTitle></SheetHeader>{selected&&<OffboardingEditor key={selected} entityId={selected==='new'?undefined:selected}/>}</SheetContent></Sheet>
  </section>;
}

export function OffboardingEditor({entityId}:{entityId?:string}){
  const client=useQueryClient();
  const [id,setId]=useState(entityId);
  const [values,setValues]=useState<Record<string,unknown>>({});
  const [dirty,setDirty]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const keys=useRef(new Map<string,string>());
  const item=useQuery({queryKey:['hrms','offboarding-detail',id??'new'],queryFn:()=>request<Detail>(id?`/hrms/offboarding/${id}`:'/hrms/offboarding/config'),refetchOnWindowFocus:false});
  const employees=useQuery({queryKey:['hrms','employees'],queryFn:()=>request<{entity_id:string;full_name:string;employee_code:string;employment_status:string}[]>('/hrms/employees')});
  const assignees=useQuery({queryKey:['hrms','offboarding-assignees'],queryFn:()=>request<{id:string;name:string}[]>('/hrms/offboarding/assignees')});
  const related=useQuery({queryKey:['hrms','offboarding-related',id],queryFn:()=>request<Record<string,{items?:Record<string,unknown>[];error?:string}>>(`/hrms/offboarding/${id}/related`),enabled:!!id});
  useEffect(()=>{if(item.data){const next={...item.data.values};if(typeof next.access_cutoff==='string'&&next.access_cutoff){const date=new Date(next.access_cutoff);if(!Number.isNaN(date.getTime()))next.access_cutoff=new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16);}setValues(next);setDirty(false);}},[item.data]);
  async function perform(trigger?:string){
    if(!item.data)return;
    setBusy(true);setError('');
    try{
      const input=Object.fromEntries(item.data.fields.filter(f=>!internal.has(f.field)&&!f.read_only&&(!id||f.field!=='employee_id')&&!(values.departure_verified==='yes'&&['confirmed_last_day','access_cutoff','exit_type'].includes(f.field))).filter(f=>values[f.field]!==undefined).map(f=>[f.field,values[f.field]]));
      if(typeof input.access_cutoff==='string'&&input.access_cutoff)input.access_cutoff=new Date(input.access_cutoff).toISOString();
      const payload={values:input,expected_hash:item.data.values_hash??'',trigger:trigger??''};
      const fingerprint=JSON.stringify([id,payload]);
      if(!keys.current.has(fingerprint))keys.current.set(fingerprint,createRequestId());
      const result=await request<{entity_id:string}>(trigger?`/hrms/offboarding/${id}/actions`:id?`/hrms/offboarding/${id}`:'/hrms/offboarding',{method:trigger||!id?'POST':'PUT',body:JSON.stringify({...payload,idempotency_key:keys.current.get(fingerprint)})});
      keys.current.clear();setId(result.entity_id);setDirty(false);
      await client.invalidateQueries({queryKey:['hrms']});
    }catch(e){setError(getApiErrorMessage(e));}finally{setBusy(false);}
  }
  if(item.isLoading)return <p role="status" className="p-6">Loading offboarding form…</p>;
  if(item.isError)return <p role="alert" className="p-6">{getApiErrorMessage(item.error)} <button onClick={()=>void item.refetch()}>Retry</button></p>;
  if(!item.data)return null;
  const d=item.data;
  const fields=d.fields.filter(f=>!internal.has(f.field)).map(f=>({...f,type:['notified_date','requested_last_day','confirmed_last_day'].includes(f.field)?'date':f.type,read_only:f.read_only||(!!id&&f.field==='employee_id')||(values.departure_verified==='yes'&&['confirmed_last_day','access_cutoff','exit_type'].includes(f.field))}));
  const form=<>{id&&d.employee_participation===false&&<p className="hrms-notice mb-4">This case uses the earlier workflow version. Employee handover assignment and automatic stage emails apply to new cases; this case retains its existing approval history.</p>}<p className="mb-3">Assigned to: {d.assignee_name||'Awaiting assignment'}</p><p className="hrms-eyebrow mb-4">{d.state??d.workflow.definition.initial_state}</p>
    {d.employee&&<p className="mb-5">{['first_name','last_name','employee_code','department','designation'].map(k=>String(d.employee?.[k]??'')).filter(Boolean).join(' · ')}</p>}
    {id&&<details className="hrms-surface p-4 mb-5"><summary>Linked assets, allocations and direct reports</summary>{related.isLoading?<p role="status">Checking linked records…</p>:related.isError?<p role="alert">Unable to check linked records. <button onClick={()=>void related.refetch()}>Retry</button></p>:Object.entries(related.data??{}).map(([label,section])=><div key={label} className="mt-3"><strong>{label.replaceAll('_',' ')}</strong>{section.error?<p role="alert">{section.error}</p>:section.items?.length?<ul>{section.items.map(r=><li key={String(r.entity_id)}>{String(r.asset_name||r.identifier||r.employee_code||r.entity_id)}{r.end_date?` · End date ${r.end_date}`:''}</li>)}</ul>:<p>No linked records found.</p>}</div>)}<p className="text-sm mt-3">Review these records and record clearance evidence below. This does not automatically return assets or end allocations.</p></details>}
    <p className="text-sm mb-5">Confirm departure at the access cutoff to mark the employee Inactive and remove HRMS access. External account removal, handover and settlement require recorded confirmation.</p>
    {error&&<p role="alert" className="hrms-notice hrms-notice--error">{error}</p>}
    <form onSubmit={e=>{e.preventDefault();void perform();}}><fieldset disabled={busy||d.editable===false} className="grid sm:grid-cols-2 gap-4"><ConfiguredInputs entityId={id} fields={fields} values={values} onChange={v=>{setValues(v);setDirty(true);}} adapters={{offboarding_approver_id:{options:assignees.data??[]},offboarding_coordinator_id:{options:assignees.data??[]},employee_id:{options:(employees.data??[]).filter(e=>e.employment_status==='active'||e.entity_id===values.employee_id).map(e=>({id:e.entity_id,name:`${e.full_name} · ${e.employee_code}`}))}}}/></fieldset>
      {d.editable!==false&&<button className="hrms-outline-button mt-5" disabled={busy||employees.isError||assignees.isError||assignees.isLoading}>Save details</button>}</form>
    {!id&&<p className="text-sm mt-3">Save the draft before uploading documents.</p>}
    {assignees.isError&&<p role="alert">Unable to load approvers and coordinators. <button onClick={()=>void assignees.refetch()}>Retry</button></p>}
    {employees.isError&&<p role="alert">Unable to load employee options. <button onClick={()=>void employees.refetch()}>Retry</button></p>}
    <div className="hrms-form-actions">{d.actions?.map(a=><button key={a.trigger} disabled={busy||dirty} className="hrms-primary-button" onClick={()=>void perform(a.trigger)}>{a.label||a.trigger.replaceAll('_',' ')}</button>)}</div>
    {dirty&&<p className="text-sm">Save changes before taking an action.</p>}
  </>;
  return <div className="p-6">{id?<RecordTabs entityId={id} workflowId={d.workflow.id} scope="offboarding">{form}</RecordTabs>:form}</div>;
}
