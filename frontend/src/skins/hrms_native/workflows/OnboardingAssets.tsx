import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { request, getApiErrorMessage } from '@/core/services/api/client';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { AssetForm, type Asset } from '../pages/AssetsPage';

type Board={assigned:Asset[];available:Asset[];can_issue:boolean;legacy_references?:string};
export function OnboardingAssets({employeeId,workflowId,employeeName,readOnly}:{employeeId:string;workflowId:string;employeeName:string;readOnly:boolean}) {
 const [adding,setAdding]=useState(false);const [selected,setSelected]=useState<Asset|null>(null);
 const query=useQuery({queryKey:['hrms','onboarding-assets',employeeId,workflowId],queryFn:()=>request<Board>(`/hrms/employee-work/${employeeId}/assets?workflow_id=${workflowId}`)});
 return <section className="rounded-xl border p-4 space-y-3" aria-label="Assets issued to this employee"><h3 className="font-semibold">Assets issued to this employee</h3>
 {query.isPending&&<p role="status">Loading issued assets…</p>}
 {query.isError&&<p role="alert">{getApiErrorMessage(query.error)} <button type="button" onClick={()=>void query.refetch()}>Retry</button></p>}
 {query.data&&<><ul className="space-y-2">{query.data.assigned.map(a=><li key={a.id}><strong>{String(a.data.asset_name??'Asset')}</strong><p>{String(a.data.asset_tag??'')} · Serial: {String(a.data.serial_number??'Not recorded')} · Issued {String(a.data.issued_date??'')}</p></li>)}</ul>
 {!query.data.assigned.length&&<p>No assets issued to this employee yet.</p>}
 {query.data.legacy_references&&<details><summary>Saved asset references</summary><p className="whitespace-pre-wrap break-words">{query.data.legacy_references}</p></details>}
 {!readOnly&&query.data.can_issue&&<button type="button" className="hrms-outline-button" onClick={()=>setAdding(true)}>Issue asset</button>}</>}
 <Sheet open={adding} onOpenChange={open=>{setAdding(open);if(!open)setSelected(null);}}><SheetContent className="hrms-brand overflow-y-auto data-[side=right]:sm:max-w-3xl"><SheetHeader><SheetTitle>Issue asset to {employeeName}</SheetTitle></SheetHeader>
 {!selected?<div className="p-6"><label>Available asset<select className="hrms-field-input" value="" onChange={e=>setSelected(query.data?.available.find(a=>a.id===e.target.value)??null)}><option value="">Select an available asset…</option>{query.data?.available.map(a=><option key={a.id} value={a.id}>{String(a.data.asset_tag)} · {String(a.data.asset_name)} · {String(a.data.serial_number??'')}</option>)}</select></label>{!query.data?.available.length&&<p>No available assets. Add inventory in Asset Management first.</p>}</div>:
 <AssetForm key={selected.id} asset={selected} action="issue" employees={[{id:employeeId,label:employeeName}]} onboarding={{employeeId,workflowId}} done={()=>{setSelected(null);setAdding(false);}}/>}
 </SheetContent></Sheet>
 </section>;
}
