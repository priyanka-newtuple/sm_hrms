import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { CheckCircle2, Circle, Clock3, Search, UserRound, CalendarDays } from 'lucide-react';
import { getApiErrorMessage, request } from '../../../core/services/api/client';
import { PageHero } from '../components/PageHero';

interface Step {
  sequence: number;
  task_id: string | null;
  title: string;
  status: string;
  readiness: 'ready' | 'waiting' | 'completed';
  owner_name: string;
  owner_role: string;
  due_date: string | null;
  depends_on: number[];
  can_complete: boolean;
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
  steps: Step[];
}

function stepLabel(step: Step) {
  if (step.readiness === 'completed') return 'Completed';
  if (step.readiness === 'waiting') return 'Waiting';
  return step.status === 'in_progress' ? 'In progress' : 'Ready';
}

export default function OnboardingPage({ caseId, embedded = false }: { caseId?: string; embedded?: boolean } = {}) {
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

  return <main className={`hrms-brand hrms-people-page ${embedded ? 'hrms-onboarding-embedded' : 'hrms-workspace-page'}`}>
    {!embedded && <PageHero title="Onboarding" intro="Every step, every owner. Help your new colleagues settle in." illustration="onboarding"
      stats={cases.data ? [
        { label: 'Open cases', value: cases.data.filter(item => item.completed_steps < item.total_steps).length },
        { label: 'Steps ready', value: cases.data.reduce((sum, item) => sum + item.steps.filter(step => step.readiness === 'ready').length, 0), tone: 'attention' },
        { label: 'Steps completed', value: cases.data.reduce((sum, item) => sum + item.completed_steps, 0), tone: 'positive' },
        { label: 'Fully onboarded', value: cases.data.filter(item => item.total_steps > 0 && item.completed_steps === item.total_steps).length },
      ] : undefined} />}
    {cases.isLoading && <p role="status" className="hrms-surface hrms-work-feedback">Loading onboarding cases…</p>}
    {cases.isError && <div role="alert" className="hrms-notice hrms-notice--error"><p>{getApiErrorMessage(cases.error)}</p><button className="hrms-outline-button" onClick={() => void cases.refetch()}>Try again</button></div>}
    {actionError && <p role="alert" className="hrms-notice hrms-notice--error">{actionError}</p>}
    {caseId && cases.data && !selected && <p role="alert">This onboarding case is no longer available to you.</p>}
    {cases.data && <div className={embedded ? '' : 'hrms-onboarding-layout'}>
      {!embedded && <aside className="hrms-case-navigation" aria-label="Onboarding employees">
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
          {selected.can_complete_case && <button type="button" disabled={completeCase.isPending} onClick={() => completeCase.mutate(selected.entity_id)} className="hrms-primary-button">{completeCase.isPending ? 'Completing…' : 'Complete onboarding'}</button>}
        </div>
        <div className="hrms-surface hrms-case-card">
          <h3 className="hrms-section-heading">Onboarding steps</h3>
          <p className="mt-1 text-sm text-slate-600">Assigned owners or an HR manager can complete ready steps here after their prerequisites are done. This onboarding plan has no separate approval step.</p>
          <ol className="hrms-step-list">{selected.steps.map((step) => <li key={step.sequence} className="hrms-step" data-readiness={step.readiness}>
            <div className="hrms-step-icon">{step.readiness === 'completed' ? <CheckCircle2 size={22} /> : step.readiness === 'waiting' ? <Clock3 size={22} /> : <Circle size={22} />}</div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center justify-between gap-2"><h4 className="font-semibold">{step.sequence}. {step.title}</h4><span className="hrms-status" data-state={step.readiness}>{stepLabel(step)}</span></div>
              <p className="hrms-step-meta"><UserRound size={14} aria-hidden="true" /> Assigned to: {step.owner_name} · Target team: {step.owner_role}</p>
              {step.due_date && <p className="hrms-step-meta"><CalendarDays size={14} aria-hidden="true" /> Due: {new Date(step.due_date).toLocaleDateString()}</p>}
              {step.depends_on.length > 0 && <p className="text-sm text-slate-600">After step {step.depends_on.join(', ')}</p>}
              {step.can_complete && <button type="button" disabled={completeStep.isPending} onClick={() => completeStep.mutate({ caseId: selected.entity_id, sequence: step.sequence })} className="hrms-outline-button hrms-step-action">{completeStep.isPending ? 'Saving…' : 'Mark complete'}</button>}
            </div>
          </li>)}</ol>
        </div>
      </section>}
    </div>}
  </main>;
}
