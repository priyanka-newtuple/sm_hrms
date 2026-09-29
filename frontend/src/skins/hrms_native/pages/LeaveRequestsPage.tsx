import { ConfiguredForm, ConfiguredField } from '../forms/ConfiguredForm';
import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getApiErrorMessage, request } from '../../../core/services/api/client';

export interface LeaveItem {
  entity_id: string;
  identifier: string;
  employee_name: string;
  start_date: string;
  end_date: string;
  leave_type: string;
  reason: string | null;
  state: string;
}

type View = 'mine' | 'approvals';

export function LeaveRow({ item, view, onChange }: { item: LeaveItem; view: View; onChange: () => void }) {
  const [error, setError] = useState('');
  const available = useQuery({
    queryKey: ['hrms', 'leave', 'available', item.entity_id, item.state],
    queryFn: () => request<{ available_transitions: { trigger: string; label: string; allowed: boolean }[] }>(`/hrms/leave-requests/${item.entity_id}/actions`),
    enabled: item.state === 'pending',
  });
  const decision = useMutation({
    mutationFn: (trigger: string) => request(`/hrms/leave-requests/${item.entity_id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ trigger, idempotency_key: crypto.randomUUID() }),
    }),
    onSuccess: () => { setError(''); onChange(); },
    onError: (cause) => setError(getApiErrorMessage(cause)),
  });
  const triggers = view === 'mine' ? ['cancel'] : ['approve', 'reject'];
  const actions = available.data?.available_transitions.filter(
    (option) => triggers.includes(option.trigger) && option.allowed
  ) ?? [];

  return (
    <li className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-semibold text-slate-900">{item.identifier || 'Leave Request'} · {item.employee_name}</p>
          <p className="mt-1 text-sm text-slate-600">{item.start_date} to {item.end_date} · {item.leave_type}</p>
          {item.reason && <p className="mt-2 text-sm text-slate-700">{item.reason}</p>}
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium capitalize text-slate-700">{item.state.replaceAll('_', ' ')}</span>
      </div>
      {actions.length > 0 && <div className="mt-4 flex gap-2">
        {actions.map((action) => <button key={action.trigger} type="button" disabled={decision.isPending}
          onClick={() => decision.mutate(action.trigger)}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium hover:bg-slate-50 disabled:opacity-50">
          {action.label || action.trigger}
        </button>)}
      </div>}
      {error && <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}
    </li>
  );
}

export default function LeaveRequestsPage() {
  const [view, setView] = useState<View>('mine');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [leaveType, setLeaveType] = useState('annual');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const queryClient = useQueryClient();
  const key = ['hrms', 'leave', view];
  const list = useQuery({
    queryKey: key,
    queryFn: () => request<LeaveItem[]>(`/hrms/leave-requests?view=${view}&limit=100`),
  });
  const create = useMutation({
    mutationFn: () => request('/hrms/leave-requests', {
      method: 'POST',
      body: JSON.stringify({ start_date: startDate, end_date: endDate, leave_type: leaveType, reason, idempotency_key: crypto.randomUUID() }),
    }),
    onSuccess: () => {
      setError(''); setStartDate(''); setEndDate(''); setReason('');
      void queryClient.invalidateQueries({ queryKey: ['hrms', 'leave'] });
    },
    onError: (cause) => setError(getApiErrorMessage(cause)),
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (endDate < startDate) { setError('End date must be on or after start date.'); return; }
    create.mutate();
  }

  return <main className="mx-auto max-w-5xl space-y-6 p-6">
    <div>
      <h1 className="text-2xl font-semibold text-slate-900">Leave Requests</h1>
      <p className="mt-1 text-sm text-slate-600">Requests and approvals use your HRMS workflow.</p>
    </div>
    <ConfiguredForm entityType="HRMS.LeaveRequest"><form onSubmit={submit} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="mb-4 text-lg font-semibold">Request leave</h2>
      <div className="grid gap-4 sm:grid-cols-2">
        <ConfiguredField field="start_date" label="Start date" className="text-sm font-medium"><input required type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} className="mt-1 block w-full rounded-lg border border-slate-300 p-2" /></ConfiguredField>
        <ConfiguredField field="end_date" label="End date" className="text-sm font-medium"><input required type="date" value={endDate} min={startDate} onChange={(event) => setEndDate(event.target.value)} className="mt-1 block w-full rounded-lg border border-slate-300 p-2" /></ConfiguredField>
        <ConfiguredField field="leave_type" label="Leave type" className="text-sm font-medium"><select value={leaveType} onChange={(event) => setLeaveType(event.target.value)} className="mt-1 block w-full rounded-lg border border-slate-300 p-2">
          {['annual', 'sick', 'casual', 'unpaid', 'other'].map((type) => <option key={type} value={type}>{type}</option>)}
        </select></ConfiguredField>
        <ConfiguredField field="reason" label="Reason" className="text-sm font-medium"><textarea value={reason} onChange={(event) => setReason(event.target.value)} maxLength={5000} rows={2} className="mt-1 block w-full rounded-lg border border-slate-300 p-2" /></ConfiguredField>
      </div>
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
      <button type="submit" disabled={create.isPending} className="mt-4 rounded-lg bg-blue-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{create.isPending ? 'Submitting…' : 'Submit request'}</button>
    </form></ConfiguredForm>
    <section>
      <div className="mb-4 flex gap-2" role="tablist" aria-label="Leave requests">
        {(['mine', 'approvals'] as const).map((tab) => <button key={tab} type="button" role="tab" aria-selected={view === tab}
          onClick={() => setView(tab)} className={`rounded-lg px-4 py-2 text-sm font-medium ${view === tab ? 'bg-blue-700 text-white' : 'bg-slate-100 text-slate-700'}`}>
          {tab === 'mine' ? 'My requests' : 'Team approvals'}
        </button>)}
      </div>
      {list.isLoading && <p>Loading requests…</p>}
      {list.isError && <p role="alert" className="text-red-700">{getApiErrorMessage(list.error)}</p>}
      {list.data?.length === 0 && <p className="rounded-xl bg-slate-50 p-6 text-sm text-slate-600">No requests in this view.</p>}
      {list.data && <ul className="space-y-3">{list.data.map((item) => <LeaveRow key={item.entity_id} item={item} view={view}
        onChange={() => void queryClient.invalidateQueries({ queryKey: ['hrms', 'leave'] })} />)}</ul>}
    </section>
  </main>;
}
