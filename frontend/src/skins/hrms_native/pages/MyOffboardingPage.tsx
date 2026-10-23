import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { request, getApiErrorMessage } from '@/core/services/api/client';
import { ConfiguredInputs, type Field } from '../forms/ConfiguredForm';
import { createRequestId } from '../requestId';

export type MyExit={entity_id:string;state:string;values:Record<string,unknown>;values_hash:string;fields:Field[];editable:boolean;assigned_to_you:boolean;actions:{trigger:string;label:string}[]};

export default function MyOffboardingPage(){
  const {id}=useParams();
  const client=useQueryClient();
  const query=useQuery({queryKey:['hrms','my-offboarding',id],queryFn:()=>request<MyExit>(`/hrms/my-offboarding/${id}`),refetchOnWindowFocus:false});
  const [values,setValues]=useState<Record<string,unknown>>({});
  const [dirty,setDirty]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const keys=useRef(new Map<string,string>());
  useEffect(()=>{if(query.data){setValues(query.data.values);setDirty(false);}},[query.data]);
  async function save(trigger=''){
    if(!query.data)return;
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
  return <section className="hrms-lk-card p-6"><h1 className="hrms-section-heading">Your offboarding</h1>
    <p className="mt-3">Current stage: <strong>{item.state}</strong></p>
    <p className="mt-2">Confirmed last working day: {String(item.values.confirmed_last_day||'Awaiting confirmation').slice(0,10)}</p>
    <p className="my-5">{item.editable?'Your handover form is assigned to you. Save your information, then submit it to HR.':'No action is required from you at this stage. You can return here to follow progress. HR will send stage updates to your agreed contact email.'}</p>
    {error&&<p role="alert" className="hrms-notice hrms-notice--error">{error}</p>}
    {item.fields.length>0&&<form onSubmit={e=>{e.preventDefault();void save();}}><fieldset disabled={!item.editable||busy} className="grid sm:grid-cols-2 gap-4"><ConfiguredInputs fields={item.fields} values={values} onChange={v=>{setValues(v);setDirty(true);}}/></fieldset>
      {item.editable&&<button disabled={busy} className="hrms-outline-button mt-5">Save details</button>}</form>}
    <div className="hrms-form-actions">{item.actions.map(a=><button key={a.trigger} disabled={busy||dirty} className="hrms-primary-button" onClick={()=>void save(a.trigger)}>{a.label}</button>)}</div>
    {dirty&&<p>Save your changes before submitting.</p>}
  </section>;
}
