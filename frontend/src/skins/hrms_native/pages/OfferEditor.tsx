import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { API_BASE, buildAuthHeaders, getApiErrorMessage, request } from '@/core/services/api/client';
import { ConfiguredInputs, type Field } from '../forms/ConfiguredForm';
import { createRequestId } from '../requestId';

type Offer = {
  entity_id?: string; values?: Record<string, unknown>; values_hash?: string;
  fields: (Field & {default?: unknown})[]; editable?: boolean; state?: string; document_current?: boolean;
  workflow: { machine_name: string; definition: { initial_state: string } };
  templates: {template_id: string; name: string}[];
  actions?: {trigger: string; label?: string; allowed?: boolean; blocked_reasons?: string[]}[];
};
const generated = new Set(['offer_pdf', 'offer_document_hash', 'offer_template_hash', 'offer_revision']);
function editableValues(item: Offer) {
  const values: Record<string,unknown> = {};
  for (const field of item.fields) if (!generated.has(field.field)) values[field.field] = item.values?.[field.field] ?? field.default ?? '';
  values.identifier = item.values?.identifier ?? '';
  if (!values.offer_template_id && item.templates.length === 1) values.offer_template_id = item.templates[0].template_id;
  if (!values.offer_date) values.offer_date = new Date().toLocaleDateString('en-CA');
  return values;
}

export function OfferEditor({entityId, machineName, onSaved}: {entityId?: string; machineName?: string; onSaved?: () => void}) {
  const client = useQueryClient();
  const [id, setId] = useState(entityId);
  const [values, setValues] = useState<Record<string,unknown>>({});
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [tab, setTab] = useState<'details'|'preview'>('details');
  const [pdf, setPdf] = useState('');
  const [pdfError, setPdfError] = useState('');
  const operationKeys = useRef(new Map<string,string>());
  function operationKey(action: string, payload: unknown) {
    const fingerprint=JSON.stringify([action,payload]);
    let value=operationKeys.current.get(fingerprint);
    if(!value){value=createRequestId();operationKeys.current.set(fingerprint,value);}
    return value;
  }
  const key = ['hrms', 'offer-document', id ?? machineName];
  const query = useQuery({queryKey:key, refetchOnWindowFocus:false, queryFn:()=>request<Offer>(id ? `/hrms/offers/${id}` : `/hrms/offers/config?machine_name=${encodeURIComponent(machineName ?? '')}`)});
  const item = query.data;
  useEffect(() => { if(item && !dirty) setValues(editableValues(item)); }, [item, dirty]);
  useEffect(() => {
    setPdf(''); setPdfError('');
    if(!id || !item?.document_current || dirty) return;
    let cancelled = false, url = '';
    void fetch(`${API_BASE}/hrms/offers/${id}/pdf`, {headers:buildAuthHeaders()}).then(async response=>{
      if(!response.ok) throw new Error('Could not load the offer PDF. Retry by reopening this offer.');
      url=URL.createObjectURL(await response.blob()); if(!cancelled)setPdf(url);
    }).catch(e=>{if(!cancelled)setPdfError(getApiErrorMessage(e));});
    return ()=>{cancelled=true;if(url)URL.revokeObjectURL(url);};
  }, [id, item, dirty]);

  async function refresh(nextId: string) {
    const fresh = await request<Offer>(`/hrms/offers/${nextId}`);
    client.setQueryData(['hrms','offer-document',nextId],fresh); setId(nextId);
    setValues(editableValues(fresh)); setDirty(false);
    void client.invalidateQueries({queryKey:['hrms','workflows']}); onSaved?.();
    return fresh;
  }
  async function save() {
    if(!item)throw new Error('Wait for the offer form to load');
    const writable=new Set(item.fields.filter(f=>!f.read_only && !generated.has(f.field)).map(f=>f.field));
    const name=values.candidate_full_name || [values.first_name,values.middle_name,values.last_name].filter(Boolean).join(' ') || 'Offer';
    const payloadValues={...Object.fromEntries(Object.entries(values).filter(([name])=>writable.has(name))),identifier:values.identifier || `${name} – ${String(values.offer_date).slice(0,10)}`};
    const result=await request<{entity_id:string}>(id ? `/hrms/offers/${id}` : '/hrms/offers', {method:id?'PUT':'POST',body:JSON.stringify({values:payloadValues,machine_name:item.workflow.machine_name,expected_hash:item.values_hash ?? '',idempotency_key:operationKey('save',[id,payloadValues,item.values_hash])})});
    return refresh(result.entity_id);
  }
  async function perform(action:'save'|'preview'|'transition',trigger?:string) {
    if(!item)return;
    setBusy(true);setError('');setNotice('');
    try {
      let current=item;
      if(action==='save' || (action==='preview' && (dirty || !id))) current=await save();
      const currentId=current.entity_id ?? id;
      if(action==='preview' && currentId){
        await request(`/hrms/offers/${currentId}/preview`,{method:'POST',body:JSON.stringify({expected_hash:current.values_hash,idempotency_key:operationKey('preview',[currentId,current.values_hash])})});
        await refresh(currentId);setTab('preview');setNotice('PDF generated. Review the preview before moving to the next state.');
      } else if(action==='transition' && currentId){
        await request(`/hrms/offers/${currentId}/actions`,{method:'POST',body:JSON.stringify({trigger,expected_hash:current.values_hash,idempotency_key:operationKey('transition',[currentId,trigger,current.values_hash])})});
        await refresh(currentId);setNotice('Offer moved to the next state.');
      } else setNotice('Offer saved. Generate a preview when ready.');
      operationKeys.current.clear();
    }catch(e){setError(getApiErrorMessage(e));}finally{setBusy(false);}
  }
  if(query.isLoading)return <p role="status" className="p-6">Loading offer…</p>;
  if(query.isError)return <div role="alert" className="p-6">{getApiErrorMessage(query.error)} <button onClick={()=>void query.refetch()}>Retry</button></div>;
  if(!item)return null;
  const editable=!id || item.editable;
  return <div className="hrms-brand p-6">
    <p className="hrms-eyebrow">{item.state ?? item.workflow.definition.initial_state}</p>
    <div className="flex gap-3 border-b mb-5"><button className="hrms-outline-button" onClick={()=>setTab('details')}>Offer details</button><button className="hrms-outline-button" onClick={()=>setTab('preview')}>PDF preview</button></div>
    {error && <p role="alert" className="hrms-notice hrms-notice--error">{error}</p>}
    {notice && <p role="status" className="hrms-notice">{notice}</p>}
    {tab==='details' ? <form onSubmit={e=>{e.preventDefault();void perform('save');}}>
      <fieldset disabled={busy || !editable} className="grid gap-4 sm:grid-cols-2">
        <label className="block space-y-1 text-sm">Offer reference (optional)<input className="hrms-field-input" value={String(values.identifier??'')} onChange={e=>{setValues({...values,identifier:e.target.value});setDirty(true);}}/></label>
        <ConfiguredInputs fields={item.fields.filter(f=>!generated.has(f.field))} values={values} onChange={v=>{setValues(v);setDirty(true);setNotice('');}} adapters={{offer_template_id:{label:'Offer letter template',options:item.templates.map(t=>({id:t.template_id,name:t.name}))}}}/>
      </fieldset>
      {editable && <div className="hrms-form-actions"><button type="submit" disabled={busy} className="hrms-outline-button">Save offer</button><button type="button" disabled={busy || !item.templates.length} className="hrms-primary-button" onClick={()=>void perform('preview')}>{busy?'Working…':'Generate PDF preview'}</button></div>}
    </form> : <div>
      {pdfError ? <p role="alert">{pdfError}</p> : pdf && !dirty ? <><a className="hrms-outline-button" href={pdf} download="Offer.pdf">Download PDF</a><iframe title="Offer letter PDF preview" src={pdf} className="w-full mt-4 rounded-xl border" style={{height:'70vh'}}/></> : <p>{item.document_current && !dirty?'Loading PDF…':'Save your details and generate a current PDF preview.'}</p>}
      {editable && <button className="hrms-primary-button mt-4" disabled={busy} onClick={()=>void perform('preview')}>Generate PDF preview</button>}
    </div>}
    {!!item.actions?.length && <div className="hrms-form-actions">{item.actions.map(a=><button type="button" key={a.trigger} className="hrms-primary-button" disabled={busy || dirty || !item.document_current || a.allowed===false} title={a.blocked_reasons?.join('; ')} onClick={()=>void perform('transition',a.trigger)}>{a.label || a.trigger}</button>)}</div>}
    {id && !item.document_current && <p className="text-sm mt-3">A current generated PDF is required before moving to the next state.</p>}
  </div>;
}
