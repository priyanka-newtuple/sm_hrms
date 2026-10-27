import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { request, getApiErrorMessage } from '@/core/services/api/client';
import { ConfiguredInputs, useFormSchema, formValues } from '../forms/ConfiguredForm';
import { createRequestId } from '../requestId';

type Unit = {serial_number:string;asset_tag:string};
type Batch = {data:Record<string,unknown>;units:Unit[];idempotency_key:string};
type Result = {complete:boolean;started?:boolean;total:number;items:{item:number;status:string;identifier?:string;message?:string}[]};
const excluded = ['identifier','hrms_operation_key','issued_employee_id','issued_by','issued_date','issue_note','serial_number','asset_tag'];

export function AddAssets({done}:{done:()=>void}) {
 const client=useQueryClient();
 const schema=useFormSchema('HRMS.Asset');
 const pending=useQuery({queryKey:['hrms','pending-asset-creations'],queryFn:()=>request<{items:Batch[]}>('/hrms/assets/pending-creations')});
 const [values,setValues]=useState<Record<string,unknown>>({});
 const [units,setUnits]=useState<Unit[]>([{serial_number:'',asset_tag:''}]);
 const [review,setReview]=useState(false);
 const [batch,setBatch]=useState<Batch|null>(null);
 const mutation=useMutation({mutationFn:(payload:Batch)=>request<Result>('/hrms/assets/batch-create',{method:'POST',body:JSON.stringify(payload)}),
   onSuccess:result=>{if(result.started===false){setBatch(null);setReview(false);}void client.invalidateQueries({queryKey:['hrms']});}});
 if(schema.isPending)return <p role="status">Loading asset form…</p>;
 if(schema.isError)return <p role="alert">{getApiErrorMessage(schema.error)} <button onClick={()=>void schema.refetch()}>Retry</button></p>;
 const fields=schema.data?.fields??[];
 const unitFields=fields.filter(f=>['serial_number','asset_tag'].includes(f.field));
 const locked=!!batch||mutation.isPending;
 function submit() {
   const payload=batch??{data:formValues(fields,values,excluded),units,idempotency_key:createRequestId()};
   setBatch(payload);mutation.mutate(payload);
 }
 return <form className="p-6 space-y-5" onSubmit={e=>{e.preventDefault();e.stopPropagation();if(review)submit();else setReview(true);}}>
 <p>Enter shared details once. Each item receives its own Asset ID automatically when saved.</p>
 {pending.isError&&<p role="alert">Could not check unfinished batches. <button type="button" onClick={()=>void pending.refetch()}>Retry</button></p>}
 {!batch&&pending.data?.items.map(p=><div className="hrms-notice" key={p.idempotency_key}>Unfinished batch: {p.units.length} × {String(p.data.asset_name??'Asset')}. <button type="button" className="hrms-outline-button" onClick={()=>{setBatch(p);setValues(p.data);setUnits(p.units);setReview(true);mutation.reset();}}>Resume batch</button></div>)}
 <fieldset disabled={locked||review} className="space-y-5">
 <label className="block">Quantity<input aria-label="Quantity" className="hrms-field-input" type="number" min={1} max={50} step={1} required value={units.length} onChange={e=>{const n=Number(e.target.value);if(Number.isInteger(n)&&n>=1&&n<=50)setUnits(old=>Array.from({length:n},(_,i)=>old[i]??{serial_number:'',asset_tag:''}));}}/></label>
 <div className="grid gap-4 sm:grid-cols-2"><ConfiguredInputs fields={fields.filter(f=>!excluded.includes(f.field))} values={values} onChange={setValues}/></div>
 <h3 className="font-semibold">Individual items</h3><p className="text-sm text-slate-500">Serial numbers identify individual equipment. Existing sticker/tag is separate from the automatic Asset ID.</p>
 {units.map((unit,i)=><section className="hrms-surface p-4 space-y-3" key={i} aria-label={`Item ${i+1}`}><strong>Item {i+1} · Asset ID assigned on save</strong><div className="grid gap-4 sm:grid-cols-2"><ConfiguredInputs fields={unitFields.map(f=>f.field==='asset_tag'?{...f,description:'Existing sticker/tag'}:f)} values={unit} onChange={v=>setUnits(old=>old.map((u,j)=>j===i?{serial_number:String(v.serial_number??''),asset_tag:String(v.asset_tag??'')}:u))}/></div></section>)}
 </fieldset>
 {review&&!batch&&<p role="status">Review {units.length} items above, then create them.</p>}
 {mutation.isError&&<p role="alert">{getApiErrorMessage(mutation.error)}. Retry this batch to check unfinished items safely.</p>}
 {mutation.data&&<section role="status"><h3>{mutation.data.items.filter(i=>i.status==='created').length} of {mutation.data.total} assets created</h3>{mutation.data.items.map(i=><p key={i.item}>Item {i.item}: {i.status==='created'?i.identifier??'Created':i.message}</p>)}</section>}
 <div className="flex justify-end gap-3"><button type="button" className="hrms-outline-button" disabled={mutation.isPending} onClick={done}>{mutation.data?.complete?'Done':'Close'}</button>{review&&!batch&&<button type="button" className="hrms-outline-button" onClick={()=>setReview(false)}>Back</button>}{!mutation.data?.complete&&<button className="hrms-primary-button" disabled={mutation.isPending}>{mutation.isPending?'Creating…':batch?'Retry unfinished items':review?`Create ${units.length} assets`:'Review assets'}</button>}</div>
 </form>;
}
