import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { CheckCircle2, Circle, Clock3, Search, UserRound, CalendarDays, MinusCircle } from 'lucide-react';
import { getApiErrorMessage, request } from '../../../core/services/api/client';
import { PageHero } from '../components/PageHero';
import { AddedSteps } from '../workflows/AddedSteps';

interface Step {
  sequence: number;
  task_id: string | null;
  title: string;
  status: string;
  readiness: 'ready' | 'waiting' | 'completed' | 'skipped';
  owner_name: string;
  owner_role: string;
  due_date: string | null;
  depends_on: number[];
  can_complete: boolean;
  can_manage?: boolean;
}

interface Case {
  entity_id: string;
  identifier: string;
  employee_entity_id: string;
  employee_name: string;
  employee_code: string;
  designation: string;
  department: string;
  state: string;
  completed_steps: number;
  total_steps: number;
  can_complete_case: boolean;
  can_cancel?: boolean;
  cancel_reason?: string | null;
  steps: Step[];
}

function stepLabel(step: Step) {
  if (step.readiness === 'skipped') return 'Skipped';
  if (step.readiness === 'completed') return 'Completed';
  if (step.readiness === 'waiting') return 'Waiting';
  return step.status === 'in_progress' ? 'In progress' : 'Ready';
}

export default function OnboardingPage({ caseId, embedded = false, showNavigation = !embedded }: { caseId?: string; embedded?: boolean; showNavigation?: boolean } = {}) {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [actionError, setActionError] = useState('');
  const cases = useQuery({
    queryKey: ['hrms', 'onboarding'],
    queryFn: () => request<Case[]>('/hrms/onboarding'),
  });
  const visible = useMemo(() => (cases.data ?? []).filter((item) =>
    `${item.employee_name} ${item.employee_code}`.toLowerCase().includes(search.toLowerCase()),
  ), [cases.data, search]);
  const selected = caseId ? cases.data?.find((item) => item.entity_id === caseId) : visible.find((item) => item.entity_id === selectedId)
    ?? visible.find((item) => item.entity_id === searchParams.get('case'))
    ?? visible[0];
  const nextSteps = selected?.steps.filter((step) => step.readiness === 'ready') ?? [];
  const completeStep = useMutation({
    mutationFn: ({ caseId, sequence }: { caseId: string; sequence: number }) => request<Case>(
      `/hrms/onboarding/${caseId}/steps/${sequence}/complete`, { method: 'POST' },
    ),
    onSuccess: () => { setActionError(''); void queryClient.invalidateQueries({ queryKey: ['hrms'] }); },
    onError: (error) => setActionError(getApiErrorMessage(error)),
  });
  const completeCase = useMutation({
    mutationFn: (caseId: string) => request<Case>(`/hrms/onboarding/${caseId}/complete`, { method: 'POST' }),
    onSuccess: () => { setActionError(''); void queryClient.invalidateQueries({ queryKey: ['hrms'] }); },
    onError: (error) => setActionError(getApiErrorMessage(error)),
  });

  // HR tools: hand a step to someone else, move its date, skip it, or cancel the whole onboarding.
  const [managing, setManaging] = useState<{ sequence: number; mode: 'reassign' | 'skip' } | 'cancel' | null>(null);
  const [change, setChange] = useState({ assigned_to: '', due_date: '', reason: '' });
  const assignees = useQuery({ queryKey: ['hrms', 'onboarding-assignees'], queryFn: () => request<{ id: string; name: string }[]>('/hrms/onboarding/assignees'),
    enabled: managing !== null && managing !== 'cancel' && managing.mode === 'reassign' });
  const manage = useMutation({
    mutationFn: ({ path, method, body }: { path: string; method: string; body: object }) => request<Case>(path, { method, body: JSON.stringify(body) }),
    onSuccess: () => { setActionError(''); setManaging(null); setChange({ assigned_to: '', due_date: '', reason: '' }); void queryClient.invalidateQueries({ queryKey: ['hrms'] }); },
    onError: (error) => setActionError(getApiErrorMessage(error)),
  });
  const open = (next: typeof managing) => { setActionError(''); setChange({ assigned_to: '', due_date: '', reason: '' }); setManaging(next); };

  const Container = embedded ? 'section' : 'main';
  return <Container className={`hrms-brand hrms-people-page ${embedded ? 'hrms-onboarding-embedded' : 'hrms-workspace-page'}`}>
    {!embedded && <PageHero title="Onboarding" intro="Every step, every owner. Help your new colleagues settle in." illustration="onboarding"
      stats={cases.data ? [
        { label: 'Open cases', value: cases.data.filter(item => item.state === 'in_progress' && item.completed_steps < item.total_steps).length },
        { label: 'Steps ready', value: cases.data.reduce((sum, item) => sum + item.steps.filter(step => step.readiness === 'ready').length, 0), tone: 'attention' },
        { label: 'Steps completed', value: cases.data.reduce((sum, item) => sum + item.completed_steps, 0), tone: 'positive' },
        { label: 'Fully onboarded', value: cases.data.filter(item => item.total_steps > 0 && item.completed_steps === item.total_steps).length },
      ] : undefined} />}
    {cases.isLoading && <p role="status" className="hrms-surface hrms-work-feedback">Loading onboarding cases…</p>}
    {cases.isError && <div role="alert" className="hrms-notice hrms-notice--error"><p>{getApiErrorMessage(cases.error)}</p><button className="hrms-outline-button" onClick={() => void cases.refetch()}>Try again</button></div>}
    {actionError && <p role="alert" className="hrms-notice hrms-notice--error">{actionError}</p>}
    {caseId && cases.data && !selected && <p role="alert">This onboarding case is no longer available to you.</p>}
    {cases.data && <div className={showNavigation ? 'hrms-onboarding-layout' : ''}>
      {showNavigation && <aside className="hrms-case-navigation" aria-label="Onboarding employees">
        <label className="hrms-search"><Search size={18} aria-hidden="true" /><input aria-label="Search onboarding employees" placeholder="Search employee or code…" value={search} onChange={(event) => setSearch(event.target.value)} className="hrms-field-input" /></label>
        <div className="hrms-surface hrms-case-list">
          {visible.length === 0 && <p className="p-4 text-slate-600">No onboarding cases found.</p>}
          {visible.map((item) => <button key={item.entity_id} type="button" onClick={() => setSelectedId(item.entity_id)} aria-pressed={selected?.entity_id === item.entity_id} className="hrms-case-button">
            <span className="block font-semibold">{item.employee_name}</span>
            <span className="block text-sm text-slate-600">{item.employee_code} · {item.department}</span>
            <span className="hrms-case-progress">{item.completed_steps}/{item.total_steps} steps complete</span>
          </button>)}
        </div>
      </aside>}
      {selected && <section className="hrms-case-detail">
        <div className="hrms-surface hrms-case-card">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><h2 className="hrms-case-name">{selected.employee_name}</h2><p className="text-slate-600">{selected.designation} · {selected.department} · {selected.employee_code}</p></div>
            <span className="hrms-status">{selected.state.replaceAll('_', ' ')}</span>
          </div>
          <div className="hrms-progress-track" role="progressbar" aria-label="Onboarding progress" aria-valuemin={0} aria-valuemax={selected.total_steps || 1} aria-valuenow={selected.completed_steps}><div style={{ width: `${selected.total_steps ? selected.completed_steps / selected.total_steps * 100 : 0}%` }} /></div>
          <p className="mt-2 text-sm text-slate-600">{selected.completed_steps} of {selected.total_steps} steps complete</p>
          {selected.state === 'completed' && selected.completed_steps < selected.total_steps && <p role="alert" className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">This case was closed with unfinished steps. HR needs to reconcile its earlier completion before further work can continue.</p>}
          <p className="hrms-next-actions"><strong>Next actions:</strong> {selected.state === 'completed' ? 'Onboarding is complete.' : nextSteps.length ? nextSteps.map((step) => step.title).join(' · ') : selected.can_complete_case ? 'Complete onboarding.' : 'Waiting for assigned work to progress'}</p>
          {selected.state === 'cancelled' && <p className="mt-3 text-sm text-slate-600">Onboarding was cancelled: {selected.cancel_reason}</p>}
          <div className="flex flex-wrap gap-2">
            {selected.can_complete_case && <button type="button" disabled={completeCase.isPending} onClick={() => completeCase.mutate(selected.entity_id)} className="hrms-primary-button">{completeCase.isPending ? 'Completing…' : 'Complete onboarding'}</button>}
            {selected.can_cancel && managing !== 'cancel' && <button type="button" onClick={() => open('cancel')} className="hrms-outline-button">Cancel onboarding</button>}
          </div>
          {selected.can_cancel && <AddedSteps entityId={selected.entity_id} />}
          {managing === 'cancel' && <form className="mt-3 space-y-2" onSubmit={(event) => { event.preventDefault(); manage.mutate({ path: `/hrms/onboarding/${selected.entity_id}/cancel`, method: 'POST', body: { reason: change.reason } }); }}>
            <label className="block space-y-1 text-sm font-medium"><span>Why is onboarding cancelled?</span><textarea required maxLength={2000} rows={2} value={change.reason} onChange={(event) => setChange({ ...change, reason: event.target.value })} className="hrms-field-input" placeholder="No-show, offer withdrawn…" /></label>
            <p className="text-sm text-slate-600">Open steps are cancelled. If they will not join, record their exit as “Did not join” in Org Directory.</p>
            <div className="flex gap-2"><button type="submit" disabled={manage.isPending} className="hrms-primary-button">Cancel onboarding</button><button type="button" onClick={() => setManaging(null)} className="hrms-outline-button">Keep it</button></div>
          </form>}
        </div>
        <div className="hrms-surface hrms-case-card">
          <h3 className="hrms-section-heading">Onboarding steps</h3>
          <p className="mt-1 text-sm text-slate-600">Assigned owners or an HR manager can complete ready steps here after their prerequisites are done. This onboarding plan has no separate approval step.</p>
          <ol className="hrms-step-list">{selected.steps.map((step) => <li key={step.sequence} className="hrms-step" data-readiness={step.readiness}>
            <div className="hrms-step-icon">{step.readiness === 'completed' ? <CheckCircle2 size={22} /> : step.readiness === 'skipped' ? <MinusCircle size={22} /> : step.readiness === 'waiting' ? <Clock3 size={22} /> : <Circle size={22} />}</div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center justify-between gap-2"><h4 className="font-semibold">{step.sequence}. {step.title}</h4><span className="hrms-status" data-state={step.readiness}>{stepLabel(step)}</span></div>
              <p className="hrms-step-meta"><UserRound size={14} aria-hidden="true" /> Assigned to: {step.owner_name} · Target team: {step.owner_role}</p>
              {step.due_date && <p className="hrms-step-meta"><CalendarDays size={14} aria-hidden="true" /> Due: {new Date(step.due_date).toLocaleDateString()}</p>}
              {step.depends_on.length > 0 && <p className="text-sm text-slate-600">After step {step.depends_on.join(', ')}</p>}
              <div className="flex flex-wrap gap-2">
                {step.can_complete && <button type="button" disabled={completeStep.isPending} onClick={() => completeStep.mutate({ caseId: selected.entity_id, sequence: step.sequence })} className="hrms-outline-button hrms-step-action">{completeStep.isPending ? 'Saving…' : 'Mark complete'}</button>}
                {step.can_manage && <button type="button" onClick={() => open({ sequence: step.sequence, mode: 'reassign' })} className="hrms-text-link">Reassign or change date</button>}
                {step.can_manage && <button type="button" onClick={() => open({ sequence: step.sequence, mode: 'skip' })} className="hrms-text-link">Skip step</button>}
              </div>
              {managing !== null && managing !== 'cancel' && managing.sequence === step.sequence && <form className="mt-2 space-y-2" onSubmit={(event) => {
                event.preventDefault();
                const path = `/hrms/onboarding/${selected.entity_id}/steps/${step.sequence}`;
                manage.mutate(managing.mode === 'skip' ? { path: `${path}/skip`, method: 'POST', body: { reason: change.reason } }
                  : { path, method: 'PATCH', body: { assigned_to: change.assigned_to || null, due_date: change.due_date || null } });
              }}>
                {managing.mode === 'reassign' ? <div className="grid gap-2 sm:grid-cols-2">
                  <label className="space-y-1 text-sm font-medium"><span>New owner</span><select value={change.assigned_to} onChange={(event) => setChange({ ...change, assigned_to: event.target.value })} className="hrms-field-input"><option value="">Keep {step.owner_name}</option>{assignees.data?.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}</select></label>
                  <label className="space-y-1 text-sm font-medium"><span>New due date</span><input type="date" value={change.due_date} onChange={(event) => setChange({ ...change, due_date: event.target.value })} className="hrms-field-input" /></label>
                </div> : <label className="block space-y-1 text-sm font-medium"><span>Why skip this step?</span><input required maxLength={2000} value={change.reason} onChange={(event) => setChange({ ...change, reason: event.target.value })} className="hrms-field-input" placeholder="Not needed for this hire…" /></label>}
                <div className="flex gap-2"><button type="submit" disabled={manage.isPending || (managing.mode === 'reassign' && !change.assigned_to && !change.due_date)} className="hrms-primary-button">{managing.mode === 'skip' ? 'Skip step' : 'Save'}</button><button type="button" onClick={() => setManaging(null)} className="hrms-outline-button">Cancel</button></div>
              </form>}
            </div>
          </li>)}</ol>
        </div>
      </section>}
    </div>}
  </Container>;
}
