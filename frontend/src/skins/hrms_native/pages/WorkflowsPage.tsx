import { OffboardingEditor } from './OffboardingPage';
import { OfferEditor } from './OfferEditor';
import CockpitPage, { CONTENT_TYPES } from './CockpitPage';
import { WfhRequestRow, type Booking } from './WorkFromHome';
import { WorkflowStages } from '../workflows/WorkflowConfiguration';
import { useSearchParams } from 'react-router-dom';
import { useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { CalendarDays, LayoutGrid, ListChecks, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import Card from '@/core/components/Card';
import { useAuth } from '@/core/auth';
import { usePersistentState } from '@/core/hooks';
import { getApiErrorMessage, request } from '@/core/services/api/client';
import { applyColumnOrder } from '@/shared/hooks/useColumnOrder';
import { resolveStateLabel } from '@/shared/utils/labels';
import ColumnVisibilityMenu from '@/shared/components/ColumnVisibilityMenu';
import type { PipelineListEntity, PipelineViewModel } from '@/shared/types/pipeline';
import PipelineListTable from '@/pages/Pipeline/components/PipelineListView/PipelineListTable';
import PipelineListToolbar from '@/pages/Pipeline/components/PipelineListView/PipelineListToolbar';
import { usePipelineList } from '@/pages/Pipeline/components/PipelineListView/usePipelineList';
import type { ColumnDescriptor, ColumnField } from '@/pages/Pipeline/components/PipelineListView/types';
import PipelineTerminalToggle from '@/pages/Pipeline/components/PipelineTerminalToggle';
import { ProjectDetail, PROJECT_KINDS } from './ProjectsPage';
import { LeaveRow, type LeaveItem } from './LeaveRequestsPage';
import { PerformanceDetail } from './PerformancePage';
import { PageHero } from '../components/PageHero';
import { EmployeeWorkflowActions } from '../workflows/EmployeeWorkflowActions';
import type { EmployeeWork } from '../workspace/useWaitingActions';
import AddEmployee from './AddEmployee';
import ExportDropdown from '@/pages/Pipeline/components/ExportDropdown';
import { FilterSelect, SearchField, Segmented } from '../components/ListKit';
import PipelineCalendarView from '@/pages/Pipeline/components/PipelineCalendarView';
import { deriveViewModelFromRecord } from '@/shared/utils/pipelineViewModel';
import { useWorkflowCatalog } from '../workflows/useWorkflowCatalog';
import { WorkflowSwimlanes } from '../workflows/WorkflowSwimlanes';

export interface WorkflowRow {
  workflow_configuration?: {machine_name:string;version:number;states:{name:string;label:string;terminal:boolean}[]};
  employee_work?: EmployeeWork;
  wfh?: Booking;
  entity_id: string;
  entity_type: string;
  title: string;
  identifier: string;
  current_state: string;
  state_label: string;
  is_terminal: boolean;
  workflow_label: string;
  owner_name: string;
  next_action: string;
  progress: string;
  due_date: string | null;
  leave: LeaveItem | null;
  leave_view: 'mine' | 'approvals' | null;
}

const MODEL: PipelineViewModel = {
  machineName: 'hrms-workflows', machineVersion: 1, entityType: 'workflow',
  machineDescription: '', states: [], terminalStates: [], transitions: [], schemaFields: [],
  stateById: new Map(), transitionById: new Map(),
};
const FIELDS: ColumnField[] = [
  { field: 'employee_name', label: 'Name' },
  { field: 'identifier', label: 'Reference' },
  { field: 'workflow', label: 'Workflow' },
  { field: 'owner', label: 'Owner' },
  { field: 'next_action', label: 'Next action' },
  { field: 'progress', label: 'Progress / dates' },
  { field: 'due_date', label: 'Due date' },
  { field: 'state', label: 'Status' },
];
const DEFAULT_FIELDS = ['employee_name', 'identifier', 'workflow', 'owner', 'next_action', 'state'];

export default function WorkflowsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [entityType, setEntityType] = useState('');
  const [view, setView] = useState<'board'|'table'|'calendar'>('board');
  const [hideTerminal, setHideTerminal] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const catalog = useWorkflowCatalog();
  const requestedWorkflow = searchParams.get('workflow');
  const workflow = catalog.data?.find(w => w.machine_name === requestedWorkflow) ?? (!requestedWorkflow ? catalog.data?.[0] : undefined);
  const model = useMemo(() => workflow ? deriveViewModelFromRecord(workflow) : MODEL, [workflow]);
  const [owner, setOwner] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(() => searchParams.get('case'));
  // Product preferences stay local; the core table remains unchanged and needs no org-write grant.
  const [columnOrder, setColumnOrder] = usePersistentState<string[]>(
    `hrms-workflow-columns:${user?.organizationId}:${user?.id}`, []);
  useEffect(() => { setSelectedId(searchParams.get('case')); }, [searchParams]);
  const query = useQuery({ queryKey: ['hrms', 'workflows'], queryFn: async () => { const rows = await request<WorkflowRow[]>('/hrms/workflows'); return rows; } });
  const workflowRows = useMemo(() => (query.data ?? []).filter(row => workflow && row.workflow_configuration?.machine_name === workflow.machine_name), [query.data, workflow]);
  const owners = useMemo(() => [...new Set(workflowRows.map(row => row.owner_name).filter(Boolean))].sort(), [workflowRows]);
  const entities = useMemo<PipelineListEntity[]>(() => workflowRows
    .filter(row => (!owner || row.owner_name === owner) && (!entityType || row.entity_type === entityType) && (!hideTerminal || !row.is_terminal))
    .map(row => ({ entity_id: row.entity_id, entity_type: row.entity_type,
      current_state: row.current_state, created_at: '', updated_at: '',
      due_date: row.due_date ?? undefined, owner_name: row.owner_name,
      data: { employee_name: row.title, identifier: row.identifier, workflow: row.workflow_label,
        due_date: row.due_date ?? '', owner: row.owner_name, next_action: row.next_action, progress: row.progress, state: row.current_state, state_label: row.state_label },
    })), [workflowRows, owner, entityType, hideTerminal]);
  const list = usePipelineList(model, entities, { extraColumns: FIELDS, defaultVisibleFields: DEFAULT_FIELDS });
  const columns = useMemo<ColumnDescriptor[]>(() => {
    const fields = FIELDS.filter(field => list.effectiveFieldIds.includes(field.field));
    return applyColumnOrder(fields.map(field => field.field), columnOrder).map(id => {
      const field = fields.find(field => field.field === id)!;
      return { id, label: field.label, render: entity => id === 'state'
        ? <span className="hrms-status" data-state={entity.current_state}>{String(entity.data.state_label || resolveStateLabel(entity.current_state))}</span>
        : <span className={id === 'employee_name' ? 'hrms-workflow-name' : ''}>{String(entity.data[id] || '—')}</span> };
    });
  }, [list.effectiveFieldIds, columnOrder]);
  const selected = query.data?.find(row => row.entity_id === selectedId);
  useEffect(() => {setOwner('');setEntityType('');list.setSearch('');list.setStateFilter('');list.setIdentifierFilter('');list.setPage(0);}, [workflow?.machine_name]);
  const states = model.states.map(s => ({id:s.name,label:s.label}));
  const visibleIds = new Set(list.filtered.map(row=>row.entity_id));
  const visibleRows = workflowRows.filter(row=>visibleIds.has(row.entity_id));
  const selectWorkflow = (machine: string) => {
    setSearchParams(previous => { const next = new URLSearchParams(previous); next.set('workflow', machine); next.delete('case'); return next; });
    setOwner(''); setEntityType(''); list.setSearch(''); list.setStateFilter(''); list.setIdentifierFilter(''); list.setPage(0);
  };
  const types = useMemo(() => [...new Set((query.data ?? []).map(row => row.entity_type))].sort(), [query.data]);
  const pageCount = Math.max(1, Math.ceil(list.totalCount / list.pageSize));

  return <main className="hrms-brand hrms-workspace-page hrms-workflows-page">
    <PageHero title="Workflows" intro="Follow progress, review next steps, and act on work in your scope." illustration="workflows"
      actions={<div className="hrms-workflow-controls"><PipelineTerminalToggle hidden={hideTerminal} label="Terminal Entities" onToggle={value => { setHideTerminal(value); list.setPage(0); }} />
        <button type="button" className="hrms-outline-button" aria-label="Refresh workflows" disabled={query.isFetching} onClick={() => void queryClient.invalidateQueries({ queryKey: ['hrms'] })}><RefreshCw size={16} strokeWidth={1.25} className={query.isFetching?'animate-spin':''}/>Refresh</button></div>}
      stats={query.data ? [
        { label: 'Records', value: workflowRows.length },
        { label: 'In progress', value: workflowRows.filter(row => !row.is_terminal).length, tone: 'attention' },
        { label: 'Completed', value: workflowRows.filter(row => row.is_terminal).length, tone: 'positive' },
        { label: 'Workflows', value: catalog.data?.length ?? '—' },
      ] : undefined} />
    {(query.isLoading || catalog.isLoading) && <p role="status">Loading workflows…</p>}
    {query.isError && <div role="alert" className="hrms-notice hrms-notice--error"><p>{getApiErrorMessage(query.error)}</p><button className="hrms-outline-button" onClick={()=>void query.refetch()}>Try again</button></div>}
    {catalog.isError && <div role="alert" className="hrms-notice hrms-notice--error">{getApiErrorMessage(catalog.error)} <button onClick={()=>void catalog.refetch()}>Retry workflows</button></div>}
    {query.data && catalog.data && <>
    <section className="hrms-surface hrms-workflow-toolbar" aria-label="Workflow controls">
      <div className="hrms-workflow-toolbar-top">
        <FilterSelect label="Workflow" value={workflow?.machine_name ?? ''} onChange={selectWorkflow}
          options={[...(!workflow ? [{value:'',label:requestedWorkflow?'Workflow unavailable':'No published workflows available'}] : []), ...catalog.data.map(item=>({value:item.machine_name,label:item.name}))]}/>
      </div>
      <div className="hrms-workflow-toolbar-views">
        <Segmented label="Workflow view" value={view} onChange={value=>setView(value as 'board'|'table'|'calendar')}
          segments={[{id:'board',label:'Board',icon:LayoutGrid},{id:'table',label:'Table',icon:ListChecks},{id:'calendar',label:'Calendar',icon:CalendarDays}]}/>
        <SearchField placeholder="Search this workflow…" value={list.search} onChange={list.setSearch}/>
      </div>
      <div className="hrms-workflow-toolbar-filters">
        <FilterSelect label="State" value={list.stateFilter} onChange={list.setStateFilter} options={[{value:'',label:'All states'},...states.map(state=>({value:state.id,label:state.label}))]}/>
        <FilterSelect label="Owner" value={owner} onChange={setOwner} options={[{value:'',label:'All owners'},...owners.map(name=>({value:name,label:name}))]}/>
        <button className="hrms-outline-button" onClick={()=>{list.setSearch('');list.setStateFilter('');list.setIdentifierFilter('');setOwner('');setHideTerminal(false);setEntityType('');}}>Clear filters</button>
      </div>
        <div className="hrms-workflow-toolbar-actions">
          <div className="hrms-workflow-export"><ExportDropdown entities={list.filtered} schemaFields={FIELDS} workflowName={workflow?.name ?? 'Workflow'}/></div>
          {workflow?.entity_type==='HRMS.Employee' && <AddEmployee/>}
        </div>
    </section>
    {workflow && (view==='board' ? <WorkflowSwimlanes rows={visibleRows} model={model} hideTerminal={hideTerminal} onOpen={setSelectedId}/> : view==='calendar' ? <PipelineCalendarView model={model} entities={list.filtered} onEntityClick={setSelectedId}/> : <Card className="hrms-surface hrms-workflow-directory">
      <PipelineListToolbar title="Workflow directory" filteredCount={list.totalCount} totalCount={workflowRows.length} entityType="workflow"
        search={list.search} onSearchChange={list.setSearch} stateFilter={list.stateFilter} onStateFilterChange={list.setStateFilter}
        states={states} entityTypes={types} entityTypeFilter={entityType} onEntityTypeFilterChange={value => { setEntityType(value); list.setPage(0); }}
        identifierFilter={list.identifierFilter} onIdentifierFilterChange={list.setIdentifierFilter} identifierOptions={list.identifierOptions}>
        <ColumnVisibilityMenu fields={FIELDS} selectedIds={list.effectiveFieldIds} visibleCount={columns.length} onToggle={list.toggleField} />
      </PipelineListToolbar>
      <PipelineListTable rows={list.rows} columns={columns} sort={list.sort} onToggleSort={list.toggleSort}
        onReorder={setColumnOrder} onEntityClick={setSelectedId}
        pagination={<div className="hrms-workflow-pagination">
          <Button className="hrms-outline-button" variant="outline" size="sm" disabled={list.page === 0} onClick={() => list.setPage(page => page - 1)}>Previous</Button>
          <span>Page {list.page + 1} of {pageCount}</span>
          <Button className="hrms-outline-button" variant="outline" size="sm" disabled={list.page + 1 >= pageCount} onClick={() => list.setPage(page => page + 1)}>Next</Button>
        </div>} />
    </Card>)}</>}
    {selected?.employee_work && <EmployeeWorkflowActions
      key={`${selected.entity_id}:${selected.employee_work.workflow_id}`}
      item={selected.employee_work} readOnly={!selected.employee_work.actions.length}
      open onOpenChange={open=>{if(!open)setSelectedId(null);}}/>}
    <Sheet open={Boolean(selected)&&!selected?.employee_work} onOpenChange={open => { if (!open) setSelectedId(null); }}>
      <SheetContent className={`hrms-brand overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-4xl hrms-review-drawer`}>
        <SheetHeader><SheetTitle>{selected?.title} · {selected?.workflow_label}</SheetTitle></SheetHeader>
        {selected && !selected.employee_work && !CONTENT_TYPES.includes(selected.entity_type) && !PROJECT_KINDS.includes(selected.entity_type) && !selected.entity_type.startsWith('HRMS.Performance') && <div className="p-6"><WorkflowStages entityId={selected.entity_id} /></div>}
        {selected && ['HRMS.PerformanceCycle', 'HRMS.PerformanceReview', 'HRMS.ProjectFeedback'].includes(selected.entity_type) && <PerformanceDetail key={selected.entity_id} entityId={selected.entity_id} />}
        {selected && PROJECT_KINDS.includes(selected.entity_type) && <ProjectDetail key={selected.entity_id} entityId={selected.entity_id} />}
        {selected && CONTENT_TYPES.includes(selected.entity_type) && <CockpitPage key={selected.entity_id} entityId={selected.entity_id} />}
        {selected?.entity_type === 'HRMS.Offboarding' && <OffboardingEditor key={selected.entity_id} entityId={selected.entity_id}/> }
        {selected && selected.entity_type.toLowerCase().replace(/[._]/g, '') === 'hrmsoffer' && <OfferEditor key={selected.entity_id} entityId={selected.entity_id} />}
        {selected?.wfh && <ul className="p-6"><WfhRequestRow item={selected.wfh} /></ul>}
          {selected?.leave && selected.leave_view && <ul className="px-6"><LeaveRow item={selected.leave} view={selected.leave_view}
          onChange={() => void queryClient.invalidateQueries({ queryKey: ['hrms'] })} /></ul>}
      </SheetContent>
    </Sheet>
  </main>;
}
