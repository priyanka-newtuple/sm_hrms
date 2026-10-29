import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { request, getApiErrorMessage } from '@/core/services/api/client';
import { ConfiguredInputs, type Field } from '../forms/ConfiguredForm';
import { createRequestId } from '../requestId';

export type MyExit={viewer?:'employee'|'participant';entity_id:string;state:string;values:Record<string,unknown>;values_hash:string;fields:Field[];sections?:{title:string;fields:Field[]}[];assets?:{identifier:string;asset_name:string}[];asset_error?:string;editable:boolean;assigned_to_you:boolean;actions:{trigger:string;label:string}[]};

export default function MyOffboardingPage(){
  const {id}=useParams();
  const client=useQueryClient();
  const [dirty,setDirty]=useState(false);
  const query=useQuery({queryKey:['hrms','my-offboarding',id],queryFn:()=>request<MyExit>(`/hrms/my-offboarding/${id}`),refetchOnWindowFocus:!dirty,refetchInterval:dirty?false:30_000});
  const [values,setValues]=useState<Record<string,unknown>>({});
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [showMissing,setShowMissing]=useState(false);
  const keys=useRef(new Map<string,string>());
  useEffect(()=>{if(query.data&&!dirty){setValues(query.data.values);}},[query.data,dirty]);
  async function save(trigger=''){
    if(!query.data)return;
    if(trigger==='submit_checklist'){
      setShowMissing(true);
      if(query.data.fields.some(f=>f.required&&!f.read_only&&(values[f.field]===false||values[f.field]==null||!String(values[f.field]).trim()))){setError('Please answer the required questions and acknowledge the declaration.');return;}
    }
    setBusy(true);setError('');
    const input=Object.fromEntries(query.data.fields.filter(f=>!f.read_only&&values[f.field]!==undefined).map(f=>[f.field,values[f.field]]));
    const payload={values:trigger?{}:input,trigger,expected_hash:query.data.values_hash};
    const fingerprint=JSON.stringify(payload);
    if(!keys.current.has(fingerprint))keys.current.set(fingerprint,createRequestId());
    try{
      await request(`/hrms/my-offboarding/${id}`,{method:'POST',body:JSON.stringify({...payload,idempotency_key:keys.current.get(fingerprint)})});
      keys.current.clear();setDirty(false);
      await client.invalidateQueries({queryKey:['hrms']});
    }catch(e){setError(getApiErrorMessage(e));}finally{setBusy(false);}
  }
  if(query.isLoading)return <p role="status">Loading your offboarding…</p>;
  if(query.isError)return <p role="alert">{getApiErrorMessage(query.error)} <button onClick={()=>void query.refetch()}>Retry</button></p>;
  if(!query.data)return null;
  const item=query.data;
  return <section className="hrms-lk-card p-6"><h1 className="hrms-section-heading">{item.viewer==='participant'?`Offboarding · ${String(item.values.exit_employee_name||item.values.identifier||'Employee')}`:'Your offboarding'}</h1>
    <p className="mt-3">Current stage: <strong>{item.state}</strong></p>
    <p className="mt-2">Confirmed last working day: {String(item.values.confirmed_last_day||'Awaiting confirmation').slice(0,10)}</p>
    <p className="my-5">{item.viewer==='participant'?'You can follow this case throughout offboarding. Assigned actions appear separately in My Tasks.':item.editable?'Complete your checklist and save a draft whenever you need. You can submit with pending items marked No. Do not enter passwords or credentials.':'Your responses are read-only at this stage. HR will send stage updates to your agreed contact email.'}</p>
    {item.editable&&!!item.values.change_reason&&<p className="hrms-notice mb-4">Changes requested: {String(item.values.change_reason)}</p>}
    {!!item.values.checklist_submitted_at&&<p className="text-sm mb-4">Last submitted: {new Date(String(item.values.checklist_submitted_at)).toLocaleString()}</p>}
    {item.asset_error?<p role="alert" className="hrms-notice">{item.asset_error}</p>:!!item.assets?.length&&<details className="hrms-surface p-4 mb-4"><summary>Assets currently assigned to you ({item.assets.length})</summary><ul>{item.assets.map(a=><li key={a.identifier}>{a.identifier} · {a.asset_name}</li>)}</ul><p>Office Admin must record returns in Asset Management.</p></details>}
    {error&&<p role="alert" className="hrms-notice hrms-notice--error">{error}</p>}
    {item.fields.length>0&&<form noValidate onSubmit={e=>{e.preventDefault();void save();}}><fieldset disabled={!item.editable||busy} className="space-y-6">
      {(item.sections?.length?item.sections:[{title:'Employee handover',fields:item.fields}]).map(section=>{
        const required=section.fields.filter(f=>f.required&&!f.read_only);
        const answered=(f:Field)=>values[f.field]!=null&&values[f.field]!==false&&String(values[f.field]).trim()!=='';
        return <section className="hrms-surface p-5" key={section.title}><div className="flex justify-between gap-4 mb-4"><h2 className="hrms-section-heading">{section.title}</h2>{required.length>0&&<span className="text-sm">{required.filter(answered).length} / {required.length} answered</span>}</div>
          <div className="grid sm:grid-cols-2 gap-4 [&_textarea]:min-h-28">{section.fields.filter(f=>!f.field.endsWith('_remarks')||values[f.field.slice(0,-8)]==='No').map(f=><div key={f.field} className={f.type==='text'||f.enum_values||f.type==='boolean'?'sm:col-span-2':''}>
            {f.enum_values&&!f.read_only?<fieldset><legend className="mb-2">{f.description}{f.required?' *':''}</legend><div className="flex gap-4 flex-wrap">{f.enum_values.map(option=><label key={option} className="flex items-center gap-2"><input type="radio" name={f.field} value={option} checked={values[f.field]===option} onChange={()=>{setValues({...values,[f.field]:option});setDirty(true);}}/>{option}</label>)}</div></fieldset>
            :<ConfiguredInputs fields={[{...f,description:(f.description??f.field)+(f.required&&!f.read_only?' *':''),required:false}]} values={values} onChange={v=>{setValues(v);setDirty(true);}}/>}
            {showMissing&&f.required&&!f.read_only&&!answered(f)&&<p role="alert" className="text-red-700 text-sm mt-1">Please complete this answer.</p>}
          </div>)}</div></section>;
      })}
      </fieldset>{item.editable&&<button disabled={busy} className="hrms-outline-button mt-5">Save draft</button>}</form>}
    <div className="hrms-form-actions">{item.actions.map(a=><button key={a.trigger} disabled={busy||dirty} className="hrms-primary-button" onClick={()=>void save(a.trigger)}>{a.label}</button>)}</div>
    {dirty&&<p>Save your changes before submitting.</p>}
  </section>;
}
