import { RecordTabs } from '../components/record/RecordTabs';
import { OnboardingAssets } from './OnboardingAssets';
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { request, getApiErrorMessage } from '@/core/services/api/client';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { ConfiguredInputs, NativeFormFields, type Field } from '../forms/ConfiguredForm';
import { createRequestId } from '../requestId';
import type { EmployeeWork } from '../workspace/useWaitingActions';

type Form = {feedback_status?:'requested'|'submitted'|'resolved'|null;previous_feedback?:string|null;asset_section?:boolean;name:string; fields:Field[]; previous_fields:Field[]; values:Record<string,unknown>; current_state:string; verifier_feedback?:string|null};
export function EmployeeWorkflowActions({item,readOnly=false,open:controlledOpen,onOpenChange}:{
  item:EmployeeWork;readOnly?:boolean;open?:boolean;onOpenChange?:(open:boolean)=>void;
}) {
  const client=useQueryClient();
  const [localOpen,setLocalOpen]=useState(false);
  const open=controlledOpen??localOpen;
  const setOpen=(value:boolean)=>{setLocalOpen(value);onOpenChange?.(value);};
  const [values,setValues]=useState<Record<string,unknown>|null>(null);
  const [key,setKey]=useState(createRequestId);
  const work=useQuery({queryKey:['hrms','employee-work'],queryFn:()=>request<EmployeeWork[]>('/hrms/employee-work'),enabled:open,refetchInterval:open?10_000:false});
  const current=work.data?.find(row=>row.entity_id===item.entity_id&&row.workflow_id===item.workflow_id);
  const changedState=!readOnly&&work.isSuccess&&(!current||current.current_state!==item.current_state);
  const form=useQuery({queryKey:['hrms','employee-state-form',item.entity_id,item.workflow_id,item.current_state],
    queryFn:()=>request<Form>(`/hrms/employee-work/${item.entity_id}/form?workflow_id=${item.workflow_id}`),enabled:open,refetchInterval:open?10_000:false});
  const stale=changedState||(!readOnly&&Boolean(form.data&&form.data.current_state!==item.current_state));
  const action=useMutation({mutationFn:async(trigger:string|null)=>{
    const latest=await work.refetch();
    const active=latest.data?.find(row=>row.entity_id===item.entity_id&&row.workflow_id===item.workflow_id);
    if(latest.isError) throw latest.error;
    if(!active||active.current_state!==item.current_state||(trigger&&!active.actions.some(step=>step.trigger===trigger)))
      throw new Error('This task has changed. Close this panel and open the current task.');
    const editable=form.data?.fields.filter(f=>!f.read_only)??[];
    const input=values??form.data?.values??{};
    const selected=item.actions.find(step=>step.trigger===trigger);
    if(selected?.required_fields?.some(f=>f.field==='hr_verification_notes'&&f.required) &&
       (typeof input.hr_verification_notes!=='string'||!input.hr_verification_notes.trim()))
      throw new Error('Enter verification notes / a correction reason before continuing.');
    const changed=Object.fromEntries(editable.filter(f=>input[f.field]!==undefined && input[f.field]!==form.data?.values[f.field]).map(f=>[f.field,input[f.field]]));
    if(Object.keys(changed).length) await request(`/hrms/employee-work/${item.entity_id}/form`,{
      method:'PUT',body:JSON.stringify({workflow_id:item.workflow_id,values:changed})});
    if(trigger) await request(`/hrms/employee-work/${item.entity_id}/actions`,{
      method:'POST',body:JSON.stringify({workflow_id:item.workflow_id,trigger,idempotency_key:key})});
  },onSuccess:()=>{setValues(null);setKey(createRequestId());setOpen(false);void client.invalidateQueries({queryKey:['hrms']});},onError:()=>{void client.invalidateQueries({queryKey:['hrms']});}});
  return <>{controlledOpen===undefined&&<button type="button" className="hrms-outline-button" onClick={()=>setOpen(true)}>{readOnly?'View details':'Open task'}</button>}
    <Sheet open={open} onOpenChange={setOpen}><SheetContent className="hrms-brand hrms-employee-form overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-3xl">
      <SheetHeader><SheetTitle>{item.title}</SheetTitle><p>{form.data?.current_state??item.current_state}</p></SheetHeader>
      <RecordTabs key={item.entity_id} entityId={item.entity_id} workflowId={item.workflow_id} scope="employee">
      {form.isLoading&&<p role="status">Loading configured form…</p>}
      {form.isError&&<p role="alert">{getApiErrorMessage(form.error)} <button onClick={()=>void form.refetch()}>Retry</button></p>}
      {stale&&<p role="status">This task has moved forward or is no longer assigned to you. Close this panel to see the current tasks.</p>}
      {work.isError&&<p role="alert">Unable to refresh task access. <button onClick={()=>void work.refetch()}>Retry</button></p>}
      {form.data&&!stale&&<form onSubmit={e=>{e.preventDefault();if(e.target===e.currentTarget)action.mutate(null);}} className="space-y-5 mt-5">
        {form.data.verifier_feedback && <section aria-label="Verifier feedback" className="rounded-xl border border-blue-200 bg-blue-50 p-4"><h3 className="font-semibold">Changes requested</h3><p className="whitespace-pre-wrap break-words mt-2">{form.data.verifier_feedback}</p></section>}
        {form.data.feedback_status==='submitted'&&<p role="status">Corrections submitted — awaiting HR review</p>}
        {form.data.previous_feedback&&<details><summary>Previous feedback · Resolved by HR</summary><p className="whitespace-pre-wrap break-words mt-2">{form.data.previous_feedback}</p><p className="hrms-muted mt-2">HR approved the details and moved onboarding forward. No correction action is pending.</p></details>}
        {!!form.data.previous_fields.length&&<details><summary>Previously entered details</summary><div className="grid gap-4 sm:grid-cols-2 mt-4"><NativeFormFields fields={form.data.previous_fields}><ConfiguredInputs entityId={item.entity_id} values={form.data.values} onChange={()=>{}}/></NativeFormFields></div></details>}
        {form.data.asset_section&&<OnboardingAssets employeeId={item.entity_id} workflowId={item.workflow_id} employeeName={item.title} readOnly={readOnly||!item.actions.length}/>}
        <h3>{form.data.name}</h3><div className="grid gap-4 sm:grid-cols-2"><NativeFormFields fields={(readOnly?form.data.fields.map(f=>({...f,read_only:true})):form.data.fields).filter(f=>!form.data?.asset_section||f.field!=='issued_asset_references')}><ConfiguredInputs entityId={item.entity_id} values={values??form.data.values} onChange={v=>{setValues(v);setKey(createRequestId());}}/></NativeFormFields></div>
        {!readOnly&&work.isSuccess&&current&&<div className="flex flex-wrap gap-3"><button className="hrms-outline-button" disabled={action.isPending} type="submit">Save details</button>
        {current.actions.map(step=><button key={step.trigger} type="button" className="hrms-primary-button" disabled={action.isPending} onClick={()=>action.mutate(step.trigger)}>{step.label||step.to_state}</button>)}</div>}
      </form>}
      {action.isError&&<p role="alert" className="text-red-700">{getApiErrorMessage(action.error)}</p>}
      </RecordTabs>
    </SheetContent></Sheet></>;
}
