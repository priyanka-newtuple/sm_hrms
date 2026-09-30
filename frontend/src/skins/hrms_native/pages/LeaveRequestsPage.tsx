import { CalendarDays, ArrowRight, CheckCircle2 } from 'lucide-react';
import { Link } from 'react-router-dom';
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
    <li className="hrms-brand hrms-surface hrms-leave-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="hrms-section-heading">{item.identifier || 'Leave Request'} · {item.employee_name}</p>
          <p className="mt-1 text-sm text-slate-600">{item.start_date} to {item.end_date} · {item.leave_type}</p>
          {item.reason && <p className="mt-2 text-sm text-slate-700">{item.reason}</p>}
        </div>
        <span className="hrms-status" data-state={item.state}>{item.state.replaceAll('_', ' ')}</span>
      </div>
      {actions.length > 0 && <div className="mt-4 flex gap-2">
        {actions.map((action) => <button key={action.trigger} type="button" disabled={decision.isPending}
          onClick={() => decision.mutate(action.trigger)}
          className={action.trigger === 'approve' ? 'hrms-primary-button' : 'hrms-outline-button'}>
          {action.label || action.trigger}
        </button>)}
      </div>}
      {available.isFetching && <p className="hrms-muted" role="status">Loading available actions…</p>}
      {available.isError && <div role="alert" className="hrms-notice hrms-notice--error">{getApiErrorMessage(available.error)} <button className="hrms-outline-button" onClick={() => void available.refetch()}>Retry actions</button></div>}
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

  return <main className="hrms-workspace-page hrms-leave-page">
    <header className="hrms-workspace-heading"><div><p className="hrms-eyebrow">TIME TO RECHARGE</p><h1>Leave requests</h1><p className="hrms-intro">Plan time away and keep your team in the loop.</p></div><Link className="hrms-outline-button" to="/hrms/workflows">View workflows <ArrowRight size={16} /></Link></header>
    <div className="hrms-leave-layout"><section className="hrms-surface hrms-leave-compose" aria-label="Request leave">
    <ConfiguredForm entityType="HRMS.LeaveRequest"><form onSubmit={submit} className="hrms-people-form">
      <div className="hrms-panel-title"><span className="hrms-work-icon"><CalendarDays size={23} strokeWidth={1.25} /></span><div><h2>Request leave</h2><p>Choose your dates and share a reason.</p></div></div>
      <div className="grid gap-4 sm:grid-cols-2">
        <ConfiguredField field="start_date" label="Start date" className="text-sm font-medium"><input required type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} className="hrms-field-input" /></ConfiguredField>
        <ConfiguredField field="end_date" label="End date" className="text-sm font-medium"><input required type="date" value={endDate} min={startDate} onChange={(event) => setEndDate(event.target.value)} className="hrms-field-input" /></ConfiguredField>
        <ConfiguredField field="leave_type" label="Leave type" className="text-sm font-medium"><select value={leaveType} onChange={(event) => setLeaveType(event.target.value)} className="hrms-field-input">
          {['annual', 'sick', 'casual', 'unpaid', 'other'].map((type) => <option key={type} value={type}>{type}</option>)}
        </select></ConfiguredField>
        <ConfiguredField field="reason" label="Reason" className="text-sm font-medium"><textarea value={reason} onChange={(event) => setReason(event.target.value)} maxLength={5000} rows={2} className="hrms-field-input" /></ConfiguredField>
      </div>
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
      <button type="submit" disabled={create.isPending} className="hrms-primary-button">{create.isPending ? 'Submitting…' : 'Submit request'}</button>
    </form></ConfiguredForm></section>
    <section className="hrms-leave-history" aria-label="Requests and approvals">
      <div className="hrms-view-switch" role="group" aria-label="Leave requests">
        {(['mine', 'approvals'] as const).map((tab) => <button key={tab} type="button" aria-pressed={view === tab}
          onClick={() => setView(tab)} className="hrms-view-button">
          {tab === 'mine' ? 'My requests' : 'Team approvals'}
        </button>)}
      </div>
      {list.isLoading && <p role="status" className="hrms-work-feedback">Loading requests…</p>}
      {list.isError && <p role="alert" className="hrms-notice hrms-notice--error">{getApiErrorMessage(list.error)}</p>}
      {list.data?.length === 0 && <div className="hrms-surface hrms-work-empty"><CheckCircle2 size={27} strokeWidth={1.25} /><h3>{view === 'mine' ? 'No leave requests yet' : 'You’re all caught up'}</h3><p>{view === 'mine' ? 'Your submitted requests will appear here.' : 'No team requests are waiting for your approval.'}</p></div>}
      {list.data && <ul className="space-y-3">{list.data.map((item) => <LeaveRow key={item.entity_id} item={item} view={view}
        onChange={() => void queryClient.invalidateQueries({ queryKey: ['hrms', 'leave'] })} />)}</ul>}
    </section></div>
  </main>;
}
