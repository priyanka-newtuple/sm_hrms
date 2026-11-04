import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Calendar, Trash2 } from 'lucide-react';
import { request, getApiErrorMessage } from '@/core/services/api/client';

type Metadata = {current_state?:string;state_entered_at?:string;due_date?:string;created_at?:string;updated_at?:string;assignee_name?:string;can_edit_due_date:boolean;can_archive:boolean};
const dateLabel=(value?:string)=>value?new Date(value).toLocaleDateString(): '—';
export function RecordToolbar({entityId,scope,workflowId,onArchived}:{entityId:string;scope:string;workflowId?:string;onArchived?:()=>void}) {
  const client=useQueryClient();
  const [confirmArchive,setConfirmArchive]=useState(false);
  const root=`/hrms/records/${entityId}/${scope}`;
  const meta=useQuery({queryKey:['hrms','record-metadata',scope,entityId,workflowId],queryFn:()=>request<Metadata>(`${root}/metadata${workflowId?`?workflow_id=${workflowId}`:''}`)});
  const change=useMutation({mutationFn:(due_date:string)=>request(`${root}/due-date`,{method:'PUT',body:JSON.stringify({due_date:due_date||null})}),onSuccess:()=>{void client.invalidateQueries({queryKey:['hrms']});}});
  const archive=useMutation({mutationFn:()=>request(root,{method:'DELETE'}),onSuccess:()=>{setConfirmArchive(false);onArchived?.();void client.invalidateQueries({queryKey:['hrms']});}});
  if(archive.isSuccess)return <p role="status" className="py-4">Record archived. Close this panel to return to the updated list.</p>;
  if(meta.isPending)return <p role="status" className="hrms-muted py-3">Loading record status…</p>;
  if(meta.isError)return <p role="alert">Could not load record controls. <button type="button" onClick={()=>void meta.refetch()}>Retry</button></p>;
  const data=meta.data;
  return <section aria-label="Record controls" className="space-y-4 py-4">
    <div className="flex flex-wrap items-center gap-3">
      {data.current_state&&<span className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-sm font-semibold text-[#0047AB]">{data.current_state}</span>}
      <label className="flex items-center gap-2 text-sm"><Calendar size={16}/>Due date<input aria-label="Due date" type="date" value={data.due_date?.slice(0,10)??''} disabled={!data.can_edit_due_date||change.isPending||archive.isSuccess} onChange={e=>change.mutate(e.target.value)} className="rounded-lg border px-2 py-1"/></label>
      {data.can_archive&&!archive.isSuccess&&<button type="button" className="ml-auto rounded-lg p-2 text-slate-500" aria-label="Archive record" title="Archive record" onClick={()=>setConfirmArchive(true)}><Trash2 size={18}/></button>}
    </div>
    {data.assignee_name&&<p className="text-sm">Assignee: <strong>{data.assignee_name}</strong></p>}
    <dl className="grid grid-cols-3 rounded-xl border text-sm divide-x">
      <div className="p-3"><dt className="hrms-muted">In this stage since</dt><dd>{dateLabel(data.state_entered_at)}</dd></div>
      <div className="p-3"><dt className="hrms-muted">Created</dt><dd>{dateLabel(data.created_at)}</dd></div>
      <div className="p-3"><dt className="hrms-muted">Updated</dt><dd>{dateLabel(data.updated_at)}</dd></div>
    </dl>
    {confirmArchive&&<div role="alert" className="rounded-xl border p-3 space-y-3"><p>Archive this record? This removes it from active workflow views. It does not delete the user account or change login access.</p><div className="flex gap-3"><button type="button" className="hrms-outline-button" onClick={()=>setConfirmArchive(false)}>Keep record</button><button type="button" className="hrms-primary-button" disabled={archive.isPending} onClick={()=>archive.mutate()}>Archive record</button></div></div>}
    {(change.isError||archive.isError)&&<p role="alert">{getApiErrorMessage(change.error??archive.error)}</p>}
  </section>;
}
