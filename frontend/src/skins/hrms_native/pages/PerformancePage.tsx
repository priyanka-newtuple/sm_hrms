import { createRequestId } from '../requestId';
import { ArrowRight, Plus, Layers, Target, MessageSquare, CheckCircle2 } from 'lucide-react';
import { WorkflowStages, useWorkflowConfiguration, transitionLabel } from '../workflows/WorkflowConfiguration';
import { ConfiguredForm, ConfiguredField } from '../forms/ConfiguredForm';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { getApiErrorMessage, request } from '@/core/services/api/client';
import { PageHero } from '../components/PageHero';

type Data = Record<string, unknown>;
interface Item { id: string; kind: string; state: string; data: Data; actions: string[]; cycle_name?: string; employee_name?: string; goals?: Item[]; feedback?: Item[] }
interface Board { cycles: Item[]; reviews: Item[]; assigned_feedback: Item[]; can_manage: boolean }
interface Person { id: string; name: string; email?: string }
interface Options { users: Person[]; employees: (Person & { manager_name: string; employee_user_id: string })[]; approvers: Person[]; calibrators: Person[] }
const label = (value: string) => value.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase());
const value = (data: Data, key: string) => String(data[key] ?? '');
const inputClass = 'hrms-field-input';
export const usePerformance = () => useQuery({ queryKey: ['hrms', 'performance'], queryFn: () => request<Board>('/hrms/performance') });

function ActionForm({ item, action, done }: { item?: Item; action: string; done: () => void }) {
  const initial = item?.data ?? {};
  const [data, setData] = useState<Data>(action === 'edit_goal' ? Object.fromEntries(
    ['title', 'description', 'category', 'measurement', 'weight', 'target_date', 'progress', 'evidence'].map(k => [k, initial[k]])) : {});
  const [participants, setParticipants] = useState<string[]>([]);
  const [calibrator, setCalibrator] = useState('');
  const [pending, setPending] = useState<{ idempotency_key: string; action: string; data: Data } | null>(null);
  const queryClient = useQueryClient();
  const cycle = action === 'create_cycle' || action === 'edit_cycle';
  const options = useQuery({ queryKey: ['hrms', 'performance-options'], queryFn: () => request<Options>('/hrms/performance/options'), enabled: cycle || action === 'reassign' });
  const reviewers = useQuery({ queryKey: ['hrms', 'performance-reviewers', item?.id], queryFn: () => request<Person[]>(`/hrms/performance/${item?.id}/reviewers`), enabled: action === 'request_feedback' });
  const mutation = useMutation({
    mutationFn: (body: NonNullable<typeof pending>) => request(action === 'create_cycle' ? '/hrms/performance/cycles' : `/hrms/performance/${item?.id}/actions`, { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ['hrms'] }); done(); },
    onError: (error) => {
      // Validation/authorization failures occur before a plan is persisted. Ambiguous network
      // failures retain the exact request and key so Retry resumes the existing operation.
      const status = (error as Error & { status?: number }).status;
      if (status === 422 || status === 403 || status === 404) setPending(null);
    },
  });
  function field(key: string, type = 'text', required = true, min?: number, max?: number) {
    return <ConfiguredField key={key} field={key} label={label(key)}>{type === 'textarea'
      ? <textarea className={inputClass} required={required} maxLength={8000} value={value(data, key)} onChange={e => setData({ ...data, [key]: e.target.value })} />
      : <input className={inputClass} required={required} type={type} min={min} max={max} value={value(data, key)} onChange={e => setData({ ...data, [key]: type === 'number' ? Number(e.target.value) : e.target.value })} />}</ConfiguredField>;
  }
  function select(key: string, people: Person[]) {
    return <ConfiguredField field={key} label={label(key.replace(/_id$/, ""))}><select className={inputClass} required value={value(data, key)} onChange={e => setData({ ...data, [key]: e.target.value })}>
      <option value="">Select…</option>{people.map(p => <option key={p.id} value={p.id}>{p.name}{p.email ? ` · ${p.email}` : ""}</option>)}</select></ConfiguredField>;
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    const body = pending ?? { idempotency_key: createRequestId(), action, data: cycle ? {
      ...data, participants: participants.map(employee_id => ({ employee_id, calibrator_user_id: calibrator })),
    } : data };
    setPending(body); mutation.mutate(body);
  }
  const goal = action === 'add_goal' || action === 'edit_goal';
  const entityType = cycle ? 'HRMS.PerformanceCycle' : goal ? 'HRMS.PerformanceGoal' : ['request_feedback','submit_feedback'].includes(action) ? 'HRMS.ProjectFeedback' : item?.kind ?? 'HRMS.PerformanceReview';
  const aliases: Record<string,string> = {approver_id:'approver_name',manager_user_id:'manager_name',calibrator_user_id:'calibrator_name',reviewer_user_id:'reviewer_name'};
  if (['submit_self','submit_manager'].includes(action)) { const prefix = action === 'submit_self' ? 'self' : 'manager'; aliases.summary = `${prefix}_summary`; aliases.rating = `${prefix}_rating`; }
  if (action === 'calibrate') { aliases.rating = 'calibrated_rating'; aliases.comment = 'calibration_comment'; }
  if (action === 'acknowledge') aliases.comment = 'employee_comment';
  if (['return_goals','return_self','return_manager'].includes(action)) aliases.comment = 'return_comment';
  if (action === 'request_changes') aliases.comment = 'approval_comment';
  return <ConfiguredForm entityType={entityType} aliases={aliases}><form className="hrms-surface hrms-people-form hrms-performance-form" onSubmit={submit}>
    <h3 className="hrms-section-heading">{label(action)}</h3>
    <fieldset disabled={Boolean(pending) || mutation.isPending} className="hrms-performance-fields disabled:opacity-70">
      {cycle && <>
        {action === 'edit_cycle' && <p className="text-sm text-muted-foreground">Enter the revised cycle details and participant list. Existing draft details are shown above.</p>}
        {field('name')}{field('description', 'textarea', false)}
        <div className="grid gap-3 sm:grid-cols-2">{['start_date', 'goal_due_date', 'self_review_due_date', 'manager_review_due_date', 'end_date'].map(key => field(key, 'date'))}</div>
        {select('approver_id', options.data?.approvers ?? [])}
        <ConfiguredField field="calibrator_user_id" label="HR calibrator"><select className={inputClass} required value={calibrator} onChange={e => setCalibrator(e.target.value)}><option value="">Select…</option>{options.data?.calibrators.map(p => <option key={p.id} value={p.id}>{p.name}{p.email ? ` · ${p.email}` : ""}</option>)}</select></ConfiguredField>
        <p className="text-sm text-muted-foreground">Select employees with active accounts and reporting managers. The employee cannot calibrate their own review.</p>
        <div className="max-h-56 space-y-2 overflow-auto rounded-lg border p-3">{options.data?.employees.map(p => <label key={p.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={participants.includes(p.id)} onChange={e => setParticipants(e.target.checked ? [...participants, p.id] : participants.filter(id => id !== p.id))} />{p.name} · Manager: {p.manager_name}</label>)}</div>
        {options.isLoading && <p>Loading participants…</p>}{options.isError && <p role="alert">{getApiErrorMessage(options.error)}</p>}
      </>}
      {goal && <>{field('title')}{field('description', 'textarea', false)}
        <ConfiguredField field="category" label="Category"><select className={inputClass} value={value(data, 'category') || 'delivery'} onChange={e => setData({ ...data, category: e.target.value })}>{['delivery', 'competency', 'leadership', 'learning', 'organization'].map(c => <option key={c}>{c}</option>)}</select></ConfiguredField>
        {field('measurement', 'textarea')}{field('weight', 'number', true, 1, 100)}{field('target_date', 'date')}{field('progress', 'number', false, 0, 100)}{field('evidence', 'textarea', false)}</>}
      {['submit_self', 'submit_manager'].includes(action) && <>{field('summary', 'textarea')}{field('rating', 'number', true, 1, 5)}</>}
      {['request_changes', 'return_goals', 'return_self', 'return_manager', 'calibrate'].includes(action) && field('comment', 'textarea')}
      {action === 'calibrate' && field('rating', 'number', true, 1, 5)}
      {action === 'reassign' && <>{select('manager_user_id', options.data?.users ?? [])}{select('calibrator_user_id', options.data?.calibrators ?? [])}{field('comment', 'textarea')}<p className="text-sm text-muted-foreground">The reason and previous assignment are retained in the action audit.</p></>}
      {action === 'acknowledge' && field('comment', 'textarea', false)}
      {action === 'request_feedback' && <>{field('project_reference')}{select('reviewer_user_id', reviewers.data ?? [])}<p className="text-sm text-muted-foreground">Choose a project reviewer. Feedback must be submitted before the manager review is completed.</p>{reviewers.isError && <p role="alert">{getApiErrorMessage(reviewers.error)}</p>}</>}
      {action === 'submit_feedback' && <>{field('rating', 'number', true, 1, 5)}{field('contribution', 'textarea')}{field('collaboration', 'textarea', false)}</>}
      {action === 'publish' && <p>Publish all calibrated reviews in this cycle. Employees will be able to see their final rating and acknowledge it.</p>}
    </fieldset>
    {mutation.isError && <p role="alert" className="text-sm text-destructive">{getApiErrorMessage(mutation.error)}{pending && ' Retry uses the same request. Keep this form open until recovery finishes.'}</p>}
    <div className="hrms-form-actions"><Button className="hrms-primary-button" variant="primary" size="md" type="submit" disabled={mutation.isPending || (cycle && !pending && (!participants.length || !calibrator))}>{mutation.isPending ? 'Saving…' : pending ? 'Retry action' : label(action)}</Button><Button className="hrms-outline-button" type="button" variant="outline" disabled={Boolean(pending)} onClick={done}>Cancel</Button></div>
  </form></ConfiguredForm>;
}

export function PerformanceDetail({ entityId }: { entityId: string }) {
  const workflowQuery=useWorkflowConfiguration();
  const configured=workflowQuery.data?.find(r=>r.entity_id===entityId);
  const query = usePerformance();
  const [action, setAction] = useState<{ name: string; item: Item } | null>(null);
  const row = [...(query.data?.cycles ?? []), ...(query.data?.reviews ?? []), ...(query.data?.assigned_feedback ?? [])].find(r => r.id === entityId);
  if (query.isError) return <p role="alert" className="p-6">{getApiErrorMessage(query.error)}</p>;
  if (!row) return <p className="p-6">{query.isLoading ? 'Loading performance workflow…' : 'This workflow is not available to your account.'}</p>;
  const readable = Object.entries(row.data).filter(([key, v]) => v !== null && v !== '' && !key.endsWith('_id') && !['participants', 'created_by', 'identifier'].includes(key));
  return <section className="hrms-brand hrms-performance-detail">
    <div><h2 className="hrms-case-name">{value(row.data, 'employee_name') || value(row.data, 'name') || row.employee_name}</h2><p className="text-sm text-muted-foreground">{row.cycle_name} · {label(row.state)}</p></div>
    <WorkflowStages entityId={entityId} />
    {row.kind === 'HRMS.PerformanceReview' && <p className="text-sm text-muted-foreground">Employee: {value(row.data, 'employee_name')} → Manager: {value(row.data, 'manager_name')} → Calibration: {value(row.data, 'calibrator_name')} → HR publication → Employee acknowledgement</p>}
    <dl className="hrms-surface hrms-detail-grid">{readable.map(([key, val]) => <div key={key}><dt className="text-xs text-muted-foreground">{label(key)}</dt><dd className="whitespace-pre-wrap break-words text-sm">{String(val)}</dd></div>)}</dl>
    {Array.isArray(row.data.participants) && <div className="hrms-surface hrms-review-card"><h3 className="font-medium">Participants</h3>{(row.data.participants as Data[]).map(p => <p key={value(p, 'employee_id')} className="mt-2 text-sm">{value(p, 'employee_name')} · Manager: {value(p, 'manager_name')} · Calibration: {value(p, 'calibrator_name')}</p>)}</div>}
    {row.goals && <div className="space-y-3"><h3 className="font-semibold">Goals · {row.goals.reduce((sum, g) => sum + Number(g.data.weight), 0)}% total weight</h3>{row.goals.map(goal => <article key={goal.id} className="hrms-surface hrms-review-card"><div className="flex justify-between gap-3"><h4 className="font-medium">{value(goal.data, 'title')} · {value(goal.data, 'weight')}%</h4><span className="text-xs">{label(goal.state)}</span></div><p className="mt-2 text-sm">{value(goal.data, 'measurement')}</p><p className="text-sm text-muted-foreground">Target: {value(goal.data, 'target_date')} · {value(goal.data, 'evidence')}</p>{Boolean(goal.data.manager_comment) && <p className="mt-2 text-sm">Manager: {value(goal.data, 'manager_comment')}</p>}{goal.actions?.map(a => <Button key={a} variant="outline" className="hrms-outline-button mt-2" onClick={() => setAction({ name: a, item: goal })}>{label(a)}</Button>)}</article>)}</div>}
    {Boolean(row.feedback?.length) && <div className="space-y-3"><h3 className="font-semibold">Project feedback</h3>{row.feedback?.map(f => <article key={f.id} className="hrms-surface hrms-review-card"><p>{value(f.data, 'project_reference')} · {value(f.data, 'reviewer_name')} · {label(f.state)}</p><p className="text-sm">{value(f.data, 'contribution')}</p><p className="text-sm">{value(f.data, 'collaboration')}</p>{Boolean(f.data.rating) && <p className="text-sm">Rating: {value(f.data, 'rating')} / 5</p>}</article>)}</div>}
    {!action && <div className="flex flex-wrap gap-2">{row.actions.map(a => <Button className="hrms-primary-button" variant="primary" size="md" key={a} onClick={() => setAction({ name: a, item: row })}>{transitionLabel(configured,a)}</Button>)}{row.actions.length === 0 && <p className="text-sm text-muted-foreground">No action is assigned to you at this stage.</p>}</div>}
    {action && <ActionForm key={`${action.item.id}:${action.name}`} item={action.item} action={action.name} done={() => setAction(null)} />}
  </section>;
}

export default function PerformancePage() {
  const query = usePerformance();
  const queryClient = useQueryClient();
  const pending = useQuery({ queryKey: ['hrms', 'performance-pending'], queryFn: () => request<{ target: string; action: string; data: Data; idempotency_key: string }[]>('/hrms/performance/pending-actions') });
  const resume = useMutation({ mutationFn: (operation: NonNullable<typeof pending.data>[number]) => request(operation.target === 'new' ? '/hrms/performance/cycles' : `/hrms/performance/${operation.target}/actions`, { method: 'POST', body: JSON.stringify({ action: operation.action, data: operation.data, idempotency_key: operation.idempotency_key }) }), onSuccess: () => queryClient.invalidateQueries({ queryKey: ['hrms'] }) });
  const [selected, setSelected] = useState<string | null>(null);
  const [create, setCreate] = useState(false);
  return <main className="hrms-workspace-page hrms-performance-page"><PageHero eyebrow="Room to grow" title="Performance" intro="Meaningful goals, thoughtful feedback, and a clear path forward." illustration="performance"
      actions={<><Link className="hrms-outline-button" to="/hrms/workflows">View workflows <ArrowRight size={16} /></Link>{query.data?.can_manage && <Button className="hrms-primary-button" variant="primary" size="md" onClick={() => setCreate(true)}><Plus size={16} />Create cycle</Button>}</>}
      stats={query.data ? [
        { label: 'Cycles', value: query.data.cycles.length },
        { label: 'Reviews', value: query.data.reviews.length },
        { label: 'Awaiting you', value: [...query.data.cycles, ...query.data.reviews, ...query.data.assigned_feedback].filter(item => item.actions.length > 0).length, tone: 'attention' },
        { label: 'Feedback requests', value: query.data.assigned_feedback.length },
      ] : undefined} />
    {query.isLoading && <p role="status" className="hrms-surface hrms-work-feedback">Loading performance…</p>}{query.isError && <div role="alert" className="hrms-notice hrms-notice--error"><p>{getApiErrorMessage(query.error)}</p><button className="hrms-outline-button" onClick={() => void query.refetch()}>Try again</button></div>}
    {pending.data?.map(operation => <div key={operation.idempotency_key} role="status" className="hrms-notice"><p>An interrupted action needs recovery: {label(operation.action)}.</p><Button className="mt-2" variant="outline" disabled={resume.isPending} onClick={() => resume.mutate(operation)}>Resume action</Button></div>)}
    {resume.isError && <p role="alert">{getApiErrorMessage(resume.error)}</p>}
    {query.data && [['Cycles', query.data.cycles], ['Employee reviews', query.data.reviews], ['Assigned project feedback', query.data.assigned_feedback]].map(([title, items]) => <section key={String(title)} className="hrms-surface hrms-performance-section"><div className="hrms-panel-title"><span className="hrms-work-icon">{title === 'Cycles' ? <Layers size={23} strokeWidth={1.25} /> : title === 'Employee reviews' ? <Target size={23} strokeWidth={1.25} /> : <MessageSquare size={23} strokeWidth={1.25} />}</span><div><h2>{String(title)}</h2><p>{title === 'Cycles' ? 'Review periods and milestones.' : title === 'Employee reviews' ? 'Goals, progress, and conversations.' : 'Your perspective on project contributions.'}</p></div><span className="hrms-work-count">{(items as Item[]).length}</span></div>{(items as Item[]).length === 0 && <div className="hrms-work-empty"><CheckCircle2 size={27} strokeWidth={1.25} /><h3>No {String(title).toLowerCase()} yet</h3><p>Items available to you will appear here.</p></div>}{(items as Item[]).length > 0 && <div className="hrms-table-scroll"><table className="hrms-people-table"><thead className="bg-muted/40"><tr><th className="p-3">Name</th><th className="p-3">Stage</th><th className="p-3">Your next action</th></tr></thead><tbody>{(items as Item[]).map(row => <tr key={row.id} className="border-t"><td className="p-3"><button className="hrms-text-link" onClick={() => setSelected(row.id)}>{value(row.data, 'name') || value(row.data, 'employee_name') || row.employee_name}</button><p className="text-xs text-muted-foreground">{row.cycle_name || value(row.data, 'project_reference')}</p></td><td className="p-3"><span className="hrms-status" data-state={row.state}>{label(row.state)}</span></td><td className="p-3">{row.actions.map(label).join(', ') || (['closed', 'acknowledged', 'submitted'].includes(row.state) ? 'Complete' : 'Waiting')}</td></tr>)}</tbody></table></div>}</section>)}
    <Sheet open={Boolean(selected) || create} onOpenChange={open => { if (!open) { setSelected(null); setCreate(false); } }}><SheetContent className="hrms-brand hrms-review-drawer overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-4xl"><SheetHeader><SheetTitle>{create ? 'Create performance cycle' : 'Performance workflow'}</SheetTitle></SheetHeader>{create ? <div className="p-6"><ActionForm action="create_cycle" done={() => setCreate(false)} /></div> : selected && <PerformanceDetail key={selected} entityId={selected} />}</SheetContent></Sheet>
  </main>;
}



