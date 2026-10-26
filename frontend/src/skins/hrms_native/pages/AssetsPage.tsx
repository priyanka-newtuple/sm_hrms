import { AssignAssets } from '../components/AssignAssets';
import { RecordTabs } from '../components/record/RecordTabs';
import { ConfiguredInputs, ConfiguredForm, useFormSchema, formValues } from '../forms/ConfiguredForm';
import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Laptop, Plus, Search } from 'lucide-react';
import { request, getApiErrorMessage } from '@/core/services/api/client';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { useHrmsCapabilities } from '../capabilities';
import { PageHero } from '../components/PageHero';

export type Asset = {id:string; data:Record<string,unknown>; state:string; employee_name:string; actions:string[]};
type Board = {items:Asset[];can_manage:boolean;employees:{id:string;label:string}[]};

const hidden = new Set(['issued_employee_id','issued_date','issued_by','issue_note','identifier','hrms_operation_key']);
const label = (s:string) => s.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());
const text = (a:Asset,k:string) => String(a.data[k]??'');

export function AssetForm({asset,action,employees,done,onboarding}:{asset?:Asset;action:string;employees:Board['employees'];done:()=>void;onboarding?:{employeeId:string;workflowId:string}}) {
 const client=useQueryClient();
 const schema=useFormSchema('HRMS.Asset');
 const [values,setValues]=useState<Record<string,unknown>>(action==='issue'?{issued_date:new Date().toLocaleDateString('en-CA'),...(onboarding?{issued_employee_id:onboarding.employeeId}:{})}:{...asset?.data});
 const [key,setKey]=useState(()=>crypto.randomUUID());
 const submitted=useRef<Record<string,unknown>|null>(null);
 const mutation=useMutation({mutationFn:()=>request(onboarding?`/hrms/employee-work/${onboarding.employeeId}/assets/${asset?.id}?workflow_id=${onboarding.workflowId}`:asset?`/hrms/assets/${asset.id}/actions`:'/hrms/assets',{method:'POST',body:JSON.stringify({action,idempotency_key:key,data:submitted.current??(submitted.current=formValues(schema.data?.fields??[],values,action==='issue'?(schema.data?.fields??[]).map(f=>f.field).filter(k=>!['issued_employee_id','issued_date','issue_note'].includes(k)):[...hidden]))})}),onError:(error)=>{
   // Duplicate identifiers are rejected before any write. Correcting one is a new
   // operation; ambiguous failures must retain the original payload and key.
   if ((error as Error & {status?:number}).status===409 && /^An asset with this (asset tag|serial number) already exists$/.test(getApiErrorMessage(error))) {
     submitted.current=null;
     setKey(crypto.randomUUID());
   }
 },onSuccess:async()=>{await client.invalidateQueries({queryKey:['hrms']});done();}});

 if(schema.isLoading)return <p role="status">Loading native form…</p>;
 if(schema.isError)return <p role="alert">{getApiErrorMessage(schema.error)} <button onClick={()=>void schema.refetch()}>Retry</button></p>;
 const retry=mutation.isError&&submitted.current!==null;
 const locked=mutation.isPending||retry;
 return <ConfiguredForm entityType="HRMS.Asset"><form className="p-6 space-y-5" onSubmit={e=>{e.preventDefault();e.stopPropagation();mutation.mutate();}}>
 <p className="text-slate-500">{action==='issue'?`Issue ${asset?.data.asset_name} to an active employee.`:'Inventory fields are configured in native Settings → Forms.'}</p>
 <fieldset disabled={locked} className="grid gap-4 sm:grid-cols-2">
 <ConfiguredInputs values={values} onChange={setValues} exclude={action==='issue'?(schema.data?.fields??[]).map(f=>f.field).filter(k=>!['issued_employee_id','issued_date','issue_note'].includes(k)):[...hidden]} adapters={{issued_employee_id:{label:'Employee',readOnly:!!onboarding,options:employees.map(e=>({id:e.id,name:e.label}))},issued_date:{type:'date'}}}/>
 </fieldset>
 {mutation.isError&&<div role="alert" className="hrms-notice hrms-notice--error">{getApiErrorMessage(mutation.error)}<p>{retry?'Retry sends the same request safely.':'Correct the asset tag or serial number, then save again.'}</p></div>}
 <div className="flex justify-end gap-3"><button type="button" className="hrms-outline-button" disabled={mutation.isPending} onClick={done}>Cancel</button><button className="hrms-primary-button" disabled={mutation.isPending}>{mutation.isPending?'Saving…':retry?'Retry':action==='issue'?'Issue asset':'Save asset'}</button></div>
 </form></ConfiguredForm>;
}

export default function AssetsPage(){
 const caps=useHrmsCapabilities();const allowed=caps.data?.capabilities.some(c=>['asset:view','asset:manage'].includes(c))??false;
 const board=useQuery({queryKey:['hrms','assets'],queryFn:()=>request<Board>('/hrms/assets'),enabled:allowed});
 const [search,setSearch]=useState('');const [status,setStatus]=useState('');const [selected,setSelected]=useState<{action:string;asset?:Asset}|null>(null);
 const [employeeFilter,setEmployeeFilter]=useState('');
 const [detail,setDetail]=useState<Asset|null>(null);
 if(caps.isLoading)return <p role="status">Loading asset access…</p>;
 if(caps.isError)return <p role="alert">Could not load access. <button onClick={()=>void caps.refetch()}>Retry</button></p>;
 if(!allowed)return <p role="alert">Asset Management is not available to your role.</p>;
 const items=board.data?.items.filter(a=>(!status||a.state===status)&&(!employeeFilter||a.data.issued_employee_id===employeeFilter)&&[...Object.values(a.data),a.employee_name].join(' ').toLowerCase().includes(search.toLowerCase()))??[];
 return <main className="hrms-workspace-page"><PageHero title="Asset Management" intro={board.data?.can_manage?'Your inventory, with a clear view of who has what.':'Equipment issued to you.'} illustration="projects" actions={board.data?.can_manage&&<><button className="hrms-outline-button" onClick={()=>setSelected({action:'issue'})}>Assign assets</button><button className="hrms-primary-button" onClick={()=>setSelected({action:'create'})}><Plus size={17}/>Add asset</button></>} stats={board.isSuccess?[{label:'Assets',value:board.data.items.length},{label:'Available',value:board.data.items.filter(a=>a.state==='available'&&!a.data.issued_employee_id).length},{label:'Issued',value:board.data.items.filter(a=>a.state==='issued').length}]:undefined}/>
 <div className="hrms-filter-bar"><label className="hrms-search"><Search size={18}/><input className="hrms-field-input" aria-label="Search assets" placeholder="Search tag, serial number, asset or employee…" value={search} onChange={e=>setSearch(e.target.value)}/></label><select className="hrms-field-input" aria-label="Asset status" value={status} onChange={e=>setStatus(e.target.value)}><option value="">All statuses</option>{[...new Set(board.data?.items.map(a=>a.state))].map(s=><option key={s} value={s}>{label(s)}</option>)}</select>{board.data?.can_manage&&<select className="hrms-field-input" aria-label="Employee assets" value={employeeFilter} onChange={e=>setEmployeeFilter(e.target.value)}><option value="">All employees</option>{board.data.employees.map(e=><option key={e.id} value={e.id}>{e.label}</option>)}</select>}</div>
 {board.isLoading&&<p role="status">Loading inventory…</p>}{board.isError&&<p role="alert" className="hrms-notice hrms-notice--error">{getApiErrorMessage(board.error)} <button onClick={()=>void board.refetch()}>Retry</button></p>}
 {board.isSuccess&&<section className="hrms-surface hrms-directory"><div className="hrms-directory-heading"><Laptop size={22}/><h2 className="hrms-section-heading">{board.data.can_manage?'Asset inventory':'My assets'}</h2></div><div className="hrms-table-scroll"><table className="hrms-people-table"><thead><tr>{['Asset','Category / serial','Location','Status','Issued to','Actions'].map(h=><th className="p-3 text-left" key={h}>{h}</th>)}</tr></thead><tbody>{items.map(a=><tr key={a.id}><td className="p-3"><button className="font-semibold text-blue-700" onClick={()=>setDetail(a)}>{text(a,'asset_name')}</button><p className="text-xs text-slate-500">{text(a,'asset_tag')}</p></td><td className="p-3">{text(a,'asset_category')}<p className="text-xs text-slate-500">{text(a,'serial_number')}</p></td><td className="p-3">{text(a,'asset_location')}</td><td className="p-3">{a.state==='available'&&a.data.issued_employee_id?'Issue in progress':label(a.state)}</td><td className="p-3">{a.employee_name}<p className="text-xs">{text(a,'issued_date')}</p></td><td className="p-3"><div className="flex gap-2">{a.actions.map(action=><button className="hrms-outline-button" key={action} onClick={()=>setSelected({action,asset:a})}>{label(action)}</button>)}</div></td></tr>)}{!items.length&&<tr><td colSpan={6} className="hrms-empty-message">{search||status?'No assets match your filters.':board.data.can_manage?'No assets yet. Add your first asset to start the inventory.':'No assets have been issued to you.'}</td></tr>}</tbody></table></div></section>}
 <Sheet open={!!selected} onOpenChange={open=>{if(!open)setSelected(null);}}><SheetContent className="hrms-brand hrms-review-drawer overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-3xl"><SheetHeader><SheetTitle>{selected?.action==='create'?'Add asset':selected?.action==='issue'?'Assign assets':'Edit asset'}</SheetTitle></SheetHeader>{selected&&(selected.action==='issue'?<AssignAssets initialAsset={selected.asset?.id} employeeId={employeeFilter||undefined} done={()=>setSelected(null)}/>:<AssetForm {...selected} employees={board.data?.employees??[]} done={()=>setSelected(null)}/>)}</SheetContent></Sheet>
 <Sheet open={!!detail} onOpenChange={open=>{if(!open)setDetail(null);}}><SheetContent className="hrms-brand overflow-y-auto"><SheetHeader><SheetTitle>{detail&&text(detail,'asset_name')}</SheetTitle></SheetHeader>{detail&&<RecordTabs key={detail.id} entityId={detail.id} scope="assets"><dl className="p-6 space-y-3">{detail&&Object.entries(detail.data).filter(([k,v])=>!['issued_by','issued_employee_id'].includes(k)&&v!=null&&v!=='').map(([k,v])=><div key={k}><dt className="text-sm text-slate-500">{label(k)}</dt><dd>{String(v)}</dd></div>)}{detail?.employee_name&&<div><dt>Issued to</dt><dd>{detail.employee_name}</dd></div>}</dl></RecordTabs>}</SheetContent></Sheet>
 </main>;
}
