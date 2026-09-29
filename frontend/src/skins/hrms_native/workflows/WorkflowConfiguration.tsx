import { useQuery } from '@tanstack/react-query';
import { request, getApiErrorMessage } from '@/core/services/api/client';
import { humanize } from '@/shared/utils/labels';
export type WorkflowConfiguration = {name:string; version:number; states:{name:string;label:string;terminal:boolean}[]; transitions:{trigger:string;label:string;from_state:string;to_state:string}[]};
export type ConfiguredWorkflowRow = {entity_id:string; current_state:string; state_label:string; is_terminal:boolean; workflow_configuration:WorkflowConfiguration};
export const useWorkflowConfiguration = () => useQuery({queryKey:['hrms','workflow-configuration'],queryFn:()=>request<ConfiguredWorkflowRow[]>('/hrms/workflows'), staleTime:0});
export function transitionLabel(row:ConfiguredWorkflowRow|undefined, action:string) {
  return row?.workflow_configuration.transitions.find(t=>t.from_state===row.current_state && t.trigger===action)?.label ?? humanize(action);
}
export function WorkflowStages({entityId}:{entityId:string}) {
  const query = useWorkflowConfiguration();
  if(query.isError) return <p role="alert">{getApiErrorMessage(query.error)}</p>;
  const row=query.data?.find(r=>r.entity_id===entityId);
  if(!row) return <p>{query.isLoading?'Loading workflow configuration…':'Workflow configuration is unavailable.'}</p>;
  const config=row.workflow_configuration;
  const stateLabel=(name:string)=>config.states.find(s=>s.name===name)?.label??humanize(name);
  const routes=config.transitions.filter(t=>t.from_state===row.current_state);
  return <section className="space-y-3"><p className="text-sm text-muted-foreground">{config.name} · Version {config.version} · Current: {row.state_label}</p>
    <ol aria-label="Workflow states" className="flex flex-wrap gap-2">{config.states.map(s=><li key={s.name} aria-current={s.name===row.current_state?'step':undefined} className={`rounded-full border px-3 py-1 text-xs ${s.name===row.current_state?'border-blue-600 bg-blue-50 text-blue-800':''}`}>{s.label}{s.terminal?' (terminal)':''}</li>)}</ol>
    <div className="rounded-lg border p-3 text-sm"><p className="font-medium">Configured transitions from this state</p>
      {routes.map(t=><p key={`${t.trigger}:${t.to_state}`}>{t.label} → {stateLabel(t.to_state)}</p>)}
      {!routes.length&&<p>No outgoing transitions.</p>}
      <p className="mt-2 text-xs text-muted-foreground">Actions below also require HRMS permissions, approval rules and workflow guards.</p>
    </div></section>;
}
