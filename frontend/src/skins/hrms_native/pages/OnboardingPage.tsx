import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { CheckCircle2, Circle, Clock3 } from 'lucide-react';
import { getApiErrorMessage, request } from '../../../core/services/api/client';

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

  return <main className="mx-auto max-w-7xl space-y-6 p-6 text-slate-900">
    {!embedded && <div>
      <h1 className="text-3xl font-semibold">Employee Onboarding</h1>
      <p className="mt-1 text-slate-600">See each new hire’s progress, next actions, and assigned owners.</p>
    </div>}
    {cases.isLoading && <p>Loading onboarding cases…</p>}
    {cases.isError && <p role="alert" className="text-red-700">{getApiErrorMessage(cases.error)}</p>}
    {actionError && <p role="alert" className="rounded-lg bg-red-50 p-3 text-red-700">{actionError}</p>}
    {caseId && cases.data && !selected && <p role="alert">This onboarding case is no longer available to you.</p>}
    {cases.data && <div className={embedded ? 'space-y-6' : 'grid gap-6 lg:grid-cols-[18rem_minmax(0,1fr)]'}>
      {!embedded && <aside className="space-y-3">
        <input aria-label="Search onboarding employees" placeholder="Search employee or code…" value={search} onChange={(event) => setSearch(event.target.value)} className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2" />
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          {visible.length === 0 && <p className="p-4 text-slate-600">No onboarding cases found.</p>}
          {visible.map((item) => <button key={item.entity_id} type="button" onClick={() => setSelectedId(item.entity_id)} className={`block w-full border-b border-slate-100 p-4 text-left last:border-0 ${selected?.entity_id === item.entity_id ? 'bg-blue-50' : 'hover:bg-slate-50'}`}>
            <span className="block font-semibold">{item.employee_name}</span>
            <span className="block text-sm text-slate-600">{item.employee_code} · {item.department}</span>
            <span className="mt-1 block text-sm text-blue-700">{item.completed_steps}/{item.total_steps} steps complete</span>
          </button>)}
        </div>
      </aside>}
      {selected && <section className="space-y-5">
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><h2 className="text-2xl font-semibold">{selected.employee_name}</h2><p className="text-slate-600">{selected.designation} · {selected.department} · {selected.employee_code}</p></div>
            <span className="rounded-full bg-blue-50 px-3 py-1 text-sm font-medium capitalize text-blue-700">{selected.state.replaceAll('_', ' ')}</span>
          </div>
          <div className="mt-5 h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full bg-blue-700" style={{ width: `${selected.total_steps ? selected.completed_steps / selected.total_steps * 100 : 0}%` }} /></div>
          <p className="mt-2 text-sm text-slate-600">{selected.completed_steps} of {selected.total_steps} steps complete</p>
          {selected.state === 'completed' && selected.completed_steps < selected.total_steps && <p role="alert" className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">This case was closed with unfinished steps. HR needs to reconcile its earlier completion before further work can continue.</p>}
          <p className="mt-4 text-sm"><strong>Next actions:</strong> {selected.state === 'completed' ? 'Onboarding is complete.' : nextSteps.length ? nextSteps.map((step) => step.title).join(' · ') : selected.can_complete_case ? 'Complete onboarding.' : 'Waiting for assigned work to progress'}</p>
          {selected.can_complete_case && <button type="button" disabled={completeCase.isPending} onClick={() => completeCase.mutate(selected.entity_id)} className="mt-4 rounded-full bg-blue-700 px-5 py-2 font-semibold text-white disabled:opacity-50">{completeCase.isPending ? 'Completing…' : 'Complete onboarding'}</button>}
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <h3 className="text-xl font-semibold">Onboarding steps</h3>
          <p className="mt-1 text-sm text-slate-600">Assigned owners or an HR manager can complete ready steps here after their prerequisites are done. This onboarding plan has no separate approval step.</p>
          <ol className="mt-5 space-y-3">{selected.steps.map((step) => <li key={step.sequence} className="flex gap-4 rounded-xl border border-slate-200 p-4">
            <div className="pt-1 text-blue-700">{step.readiness === 'completed' ? <CheckCircle2 size={22} /> : step.readiness === 'waiting' ? <Clock3 size={22} /> : <Circle size={22} />}</div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center justify-between gap-2"><h4 className="font-semibold">{step.sequence}. {step.title}</h4><span className={`rounded-full px-3 py-1 text-xs font-medium ${step.readiness === 'ready' ? 'bg-blue-100 text-blue-800' : step.readiness === 'completed' ? 'bg-green-100 text-green-800' : 'bg-slate-100 text-slate-700'}`}>{stepLabel(step)}</span></div>
              <p className="mt-1 text-sm text-slate-600">Assigned to: {step.owner_name} · Target team: {step.owner_role}</p>
              {step.due_date && <p className="text-sm text-slate-600">Due: {new Date(step.due_date).toLocaleDateString()}</p>}
              {step.depends_on.length > 0 && <p className="text-sm text-slate-600">After step {step.depends_on.join(', ')}</p>}
              {step.can_complete && <button type="button" disabled={completeStep.isPending} onClick={() => completeStep.mutate({ caseId: selected.entity_id, sequence: step.sequence })} className="mt-3 rounded-full border border-blue-700 px-4 py-1.5 text-sm font-semibold text-blue-700 disabled:opacity-50">{completeStep.isPending ? 'Saving…' : 'Mark complete'}</button>}
            </div>
          </li>)}</ol>
        </div>
      </section>}
    </div>}
  </main>;
}
