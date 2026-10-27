import { useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { request, getApiErrorMessage } from '@/core/services/api/client';
import { EmployeeWorkflowActions } from '../workflows/EmployeeWorkflowActions';
import type { EmployeeWork } from '../workspace/useWaitingActions';

type Entry = EmployeeWork & {states:string[];workflow_version:number;completed:boolean; assigned_to:string|null; started_by:string|null};
export function OnboardingTracker({actions, notice}: {actions?: ReactNode; notice?: ReactNode}) {
 const [status,setStatus]=useState('progress');
 const [search,setSearch]=useState('');
 const query=useQuery({queryKey:['hrms','onboarding-tracker'],queryFn:()=>request<Entry[]>('/hrms/onboarding-tracker'),refetchInterval:30000});
 const rows=(query.data??[]).filter(r=>(status==='all'||r.completed===(status==='complete'))&&`${r.title} ${r.current_state} ${r.assigned_to??''} ${r.started_by??''}`.toLowerCase().includes(search.toLowerCase()));
 return <section className="hrms-lk-card" aria-label="Employee onboarding progress">
  <div className="hrms-lk-card-head"><h2 className="hrms-section-heading">Employee onboarding</h2><div>{actions}</div></div>
  <div className="p-6">{notice}<p className="hrms-muted">Track progress across every step, including tasks assigned to others.</p>
   <div className="flex flex-wrap gap-3 mt-4"><input aria-label="Search onboarding" className="hrms-field-input" placeholder="Search employee, step or owner…" value={search} onChange={e=>setSearch(e.target.value)}/>
   <select aria-label="Onboarding status" className="hrms-field-input" value={status} onChange={e=>setStatus(e.target.value)}><option value="progress">In progress</option><option value="complete">Completed</option><option value="all">All</option></select></div></div>
  {query.isPending?<p role="status" className="p-6">Loading onboarding…</p>:query.isError?<div role="alert" className="p-6">{getApiErrorMessage(query.error)} <button className="hrms-outline-button" onClick={()=>void query.refetch()}>Retry</button></div>:rows.length?<div className="hrms-lk-scroll"><table className="hrms-lk-table"><thead><tr><th>Employee</th><th>Current step</th><th>Assigned to</th><th>Started by</th><th>Due date</th><th>Actions</th></tr></thead><tbody>
  {rows.map(r=><tr key={`${r.entity_id}-${r.workflow_id}`}><td>{r.title}<span className="hrms-lk-sub">{r.workflow_label}</span></td><td>{r.current_state}</td><td>{r.assigned_to||'No individual assigned'}</td><td>{r.started_by||'Unavailable'}</td><td>{r.due_date?new Date(r.due_date).toLocaleDateString():'No due date'}</td><td><div className="flex flex-wrap gap-2"><EmployeeWorkflowActions item={r} readOnly={!r.actions.length}/><details><summary className="hrms-text-link cursor-pointer">View workflow</summary><p>Version {r.workflow_version}</p><ol aria-label="Workflow steps">{r.states.map(state=><li key={state} aria-current={state===r.current_state?'step':undefined} className={state===r.current_state?'font-semibold text-blue-700':''}>{state}</li>)}</ol></details></div></td></tr>)}
  </tbody></table></div>:<p className="p-6">{search?'No employees match your search.':status==='complete'?'No completed onboardings yet.':'No employees in this view.'}</p>}
 </section>;
}
