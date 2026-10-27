import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { request, getApiErrorMessage } from '@/core/services/api/client';
import type { Asset } from '../pages/AssetsPage';

type Payload = {asset_ids:string[];data:Record<string,string>;idempotency_key:string};
type Result = {complete:boolean;started?:boolean;items:{asset_id:string;status:string;message?:string}[]};
type Board = {items:Asset[];employees:{id:string;label:string}[]};
export function AssignAssets({initialAsset,employeeId,workflowId,done}:{initialAsset?:string;employeeId?:string;workflowId?:string;done:()=>void}) {
 const client=useQueryClient();
 const board=useQuery({queryKey:['hrms','assets'],queryFn:()=>request<Board>('/hrms/assets')});
 const [employee,setEmployee]=useState(employeeId??'');
 const [employeeSearch,setEmployeeSearch]=useState('');
 const [selected,setSelected]=useState<string[]>(initialAsset?[initialAsset]:[]);
 const [search,setSearch]=useState('');const [category,setCategory]=useState('');const [location,setLocation]=useState('');
 const [date,setDate]=useState(()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;});
 const [note,setNote]=useState('');const [review,setReview]=useState(false);
 const [payload,setPayload]=useState<Payload|null>(null);
 const pending=useQuery({queryKey:['hrms','pending-asset-assignments'],queryFn:()=>request<{items:Payload[]}>('/hrms/assets/pending-assignments')});
 const mutation=useMutation({mutationFn:async(p:NonNullable<typeof payload>)=>request<Result>(employeeId&&workflowId?`/hrms/employee-work/${employeeId}/assets/assign?workflow_id=${workflowId}`:'/hrms/assets/assign',{method:'POST',body:JSON.stringify(p)}),onSuccess:(result)=>{if(result.started===false){setPayload(null);setReview(false);}void client.invalidateQueries({queryKey:['hrms']});}});
 if(board.isPending)return <p role="status">Loading inventory…</p>;
 if(board.isError)return <p role="alert">{getApiErrorMessage(board.error)} <button type="button" onClick={()=>void board.refetch()}>Retry</button></p>;
 const available=board.data.items.filter(a=>a.actions.includes('issue'));
 const picked=board.data.items.filter(a=>selected.includes(a.id));
 const holdings=board.data.items.filter(a=>a.data.issued_employee_id===employee);
 const visible=available.filter(a=>(!category||a.data.asset_category===category)&&(!location||a.data.asset_location===location)&&Object.values(a.data).join(' ').toLowerCase().includes(search.toLowerCase()));
 const submit=()=>{const p=payload??{asset_ids:selected,data:{issued_employee_id:employee,issued_date:date,issue_note:note},idempotency_key:crypto.randomUUID()};setPayload(p);mutation.mutate(p);};
 return <div className="p-6 space-y-5">
 <p className="text-slate-500">Assign equipment that has been handed over. Select several assets and enter the handover details once.</p>
 {pending.isError&&<p role="alert">Could not load unfinished assignments. <button type="button" onClick={()=>void pending.refetch()}>Retry</button></p>}
 {!payload&&pending.data?.items.filter(p=>!employeeId||p.data.issued_employee_id===employeeId).map(p=><div className="hrms-notice" key={p.idempotency_key}>An earlier assignment of {p.asset_ids.length} assets is unfinished. <button type="button" className="hrms-outline-button" onClick={()=>{setPayload(p);setEmployee(p.data.issued_employee_id);setSelected(p.asset_ids);setDate(p.data.issued_date);setNote(p.data.issue_note??'');setReview(true);mutation.reset();}}>Resume assignment</button></div>)}
 <fieldset disabled={!!payload} className="space-y-4">
 {!employeeId&&<><input className="hrms-field-input" aria-label="Search employees" placeholder="Search employee name, code or email…" value={employeeSearch} onChange={e=>setEmployeeSearch(e.target.value)}/><label>Employee<select className="hrms-field-input" value={employee} onChange={e=>setEmployee(e.target.value)}><option value="">Choose employee</option>{board.data.employees.filter(e=>e.id===employee||e.label.toLowerCase().includes(employeeSearch.toLowerCase())).map(e=><option key={e.id} value={e.id}>{e.label}</option>)}</select></label></>}
 {employee&&<section className="hrms-surface p-4"><strong>{board.data.employees.find(e=>e.id===employee)?.label??'Selected employee'}</strong><p>Currently assigned: {holdings.length} assets</p><ul>{holdings.map(a=><li key={a.id}>{String(a.data.identifier??a.data.asset_tag??'')} · {String(a.data.asset_name??'')}</li>)}</ul></section>}
 {!review&&<><div className="flex gap-2 flex-wrap"><input className="hrms-field-input" aria-label="Search available assets" placeholder="Search tag, serial or model…" value={search} onChange={e=>setSearch(e.target.value)}/>{(['asset_category','asset_location'] as const).map((field,i)=><select key={field} className="hrms-field-input" aria-label={i?'Location':'Category'} value={i?location:category} onChange={e=>(i?setLocation:setCategory)(e.target.value)}><option value="">All {i?'locations':'categories'}</option>{[...new Set(available.map(a=>String(a.data[field]??'')).filter(Boolean))].map(v=><option key={v}>{v}</option>)}</select>)}</div>
 <div className="max-h-72 overflow-y-auto space-y-2">{visible.map(a=><label key={a.id} className="hrms-surface p-3 flex gap-3 items-start"><input type="checkbox" checked={selected.includes(a.id)} onChange={e=>setSelected(e.target.checked?[...selected,a.id]:selected.filter(id=>id!==a.id))}/><span><strong>{String(a.data.asset_name??'')} · {String(a.data.identifier??a.data.asset_tag??'')}</strong><br/>{['model','serial_number','asset_condition','asset_location'].map(k=>a.data[k]).filter(Boolean).join(' · ')}</span></label>)}{!visible.length&&<p>{available.length ? 'No available assets match these filters.' : 'No assets available for assignment. Add equipment in Asset Management, then reopen this panel.'}</p>}</div></>}
 <section>{selected.length>50&&<p role="alert">Select up to 50 assets per assignment.</p>}<h3 className="font-semibold">Selected assets ({selected.length})</h3>{picked.map(a=><div className="flex justify-between py-2" key={a.id}><span>{String(a.data.identifier??a.data.asset_tag??'')} · {String(a.data.asset_name??'')}</span>{!review&&<button type="button" onClick={()=>setSelected(selected.filter(id=>id!==a.id))}>Remove</button>}</div>)}</section>
 <label className="block">Assignment date<input type="date" className="hrms-field-input" value={date} onChange={e=>setDate(e.target.value)}/></label>
 <label className="block">Handover note (optional)<textarea className="hrms-field-input" maxLength={2000} value={note} onChange={e=>setNote(e.target.value)}/></label>
 </fieldset>
 {mutation.isError&&<p role="alert">{getApiErrorMessage(mutation.error)}. Retry checks the same assignment safely.</p>}
 {mutation.data&&<section role="status"><h3>{mutation.data.items.filter(i=>i.status==='assigned').length} of {selected.length} assets assigned</h3>{mutation.data.items.map(i=><p key={i.asset_id}>{String(board.data.items.find(a=>a.id===i.asset_id)?.data.asset_tag??i.asset_id)}: {i.status==='assigned'?'Assigned':i.message??'Incomplete'}</p>)}</section>}
 <div className="flex justify-end gap-3"><button type="button" className="hrms-outline-button" disabled={mutation.isPending} onClick={done}>{mutation.data?.complete?'Done':'Close'}</button>{review&&!payload&&<button type="button" className="hrms-outline-button" onClick={()=>setReview(false)}>Back</button>}{!mutation.data?.complete&&<button type="button" className="hrms-primary-button" disabled={!employee||!selected.length||selected.length>50||!date||mutation.isPending} onClick={()=>review?submit():setReview(true)}>{mutation.isPending?'Assigning…':payload?'Retry unfinished assignments':review?`Assign ${selected.length} assets`:'Review assignment'}</button>}</div>
 </div>;
}
