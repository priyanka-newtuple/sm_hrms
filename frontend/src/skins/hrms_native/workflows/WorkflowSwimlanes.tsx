import { LayoutGrid, UserRound } from 'lucide-react';
import { KanbanCardContent } from '@/pages/Pipeline/components/PipelineKanbanBoard/KanbanCardContent';
import type { PipelineViewModel } from '@/shared/types/pipeline';
import type { WorkflowRow } from '../pages/WorkflowsPage';

/** Presentation only: actions open the existing permission-scoped HRMS form. */
export function WorkflowSwimlanes({rows,model,hideTerminal,onOpen}:{rows:WorkflowRow[];model:PipelineViewModel;hideTerminal:boolean;onOpen:(id:string)=>void}) {
  const states = model.states.filter(state=>!hideTerminal||!state.isTerminal);
  const historic = [...new Map(rows.filter(row=>!model.states.some(state=>state.name===row.current_state)).map(row=>[row.current_state,row])).values()];
  const card = (row:WorkflowRow) => <button key={row.entity_id} className="hrms-swimlane-card" onClick={()=>onOpen(row.entity_id)}>
    <KanbanCardContent entity={{id:row.entity_id,title:row.title,subtitle:row.identifier,stateId:row.current_state,dueDate:row.due_date??undefined}} inState={null}>
      <span className="flex gap-2 mt-3"><UserRound size={14}/>{row.owner_name||'No individual assigned'}</span>
    </KanbanCardContent>
    {row.next_action&&<p>{row.next_action}</p>}
    <span className="hrms-swimlane-open">Open details →</span>
  </button>;
  return <section className="hrms-surface hrms-swimlanes" aria-label="Workflow swimlanes">
    <header className="hrms-workflow-board-heading"><span className="hrms-workflow-board-icon" aria-hidden="true"><LayoutGrid size={17}/></span><h2>Workflow board</h2><span className="hrms-workflow-board-meta">{states.length + historic.length} columns · {rows.length} records in your scope</span></header>
    <div className="hrms-swimlane-scroll" tabIndex={0} aria-label="Workflow stages; scroll horizontally">
      {states.map((state,index)=>{
        const cards=rows.filter(row=>row.current_state===state.name);
        return <section className="hrms-swimlane" key={state.name} aria-label={state.label}>
          <header><small>#{index+1}</small><span className="hrms-swimlane-dot"/><h3>{state.label}</h3><span className="hrms-swimlane-count">{cards.length}</span></header>
          {(state.isInitial||state.isTerminal)&&<span className="hrms-swimlane-terminal">{state.isInitial?'Initial':'Terminal'}</span>}
          <p className="text-xs text-muted-foreground mb-3">Out {state.outgoingCount} · In {state.incomingCount}</p>
          <div className="hrms-swimlane-cards">{cards.length?cards.map(card):<p className="hrms-swimlane-empty">No matching records in your scope</p>}</div>
        </section>;
      })}
      {historic.map(row=><section className="hrms-swimlane" key={row.current_state}><header><h3>{row.state_label}</h3></header><small>Earlier workflow version</small><div className="hrms-swimlane-cards">{rows.filter(item=>item.current_state===row.current_state).map(card)}</div></section>)}
    </div>
  </section>;
}
