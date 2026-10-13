import { createRequestId } from '../requestId';
import { CalendarDays, ArrowRight, CheckCircle2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { ConfiguredForm, ConfiguredInputs, useFormSchema, commandValues } from '../forms/ConfiguredForm';
import { CustomFieldValues, type CustomValues } from '../forms/CustomFields';
import { AddedSteps } from '../workflows/AddedSteps';
import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getApiErrorMessage, request } from '../../../core/services/api/client';
import { useHrmsCapabilities } from '../capabilities';
import { PageHero } from '../components/PageHero';

export interface LeaveItem {
  entity_id: string;
  identifier: string;
  employee_name: string;
  start_date: string;
  end_date: string;
  /** Working days: weekdays that are not published holidays. */
  days?: number;
  leave_type: string;
  reason: string | null;
  state: string;
  custom?: CustomValues;
}

type View = 'mine' | 'approvals';

export function LeaveRow({ item, view, onChange }: { item: LeaveItem; view: View; onChange: () => void }) {
  const [error, setError] = useState('');
  const available = useQuery({
    queryKey: ['hrms', 'leave', 'available', item.entity_id, item.state],
    queryFn: () => request<{ available_transitions: { trigger: string; label: string; allowed: boolean }[] }>(`/hrms/leave-requests/${item.entity_id}/actions`),
    // The employee may also cancel their approved leave until it starts; the server decides.
    enabled: item.state === 'pending' || (view === 'mine' && item.state === 'approved'),
  });
  const decision = useMutation({
    mutationFn: (trigger: string) => request(`/hrms/leave-requests/${item.entity_id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ trigger, idempotency_key: createRequestId() }),
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
          <CustomFieldValues entityType="HRMS.LeaveRequest" values={item.custom} />
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
      {view === 'approvals' && <div className="mt-3"><AddedSteps entityId={item.entity_id} onDemand /></div>}
      {available.isFetching && <p className="hrms-muted" role="status">Loading available actions…</p>}
      {available.isError && <div role="alert" className="hrms-notice hrms-notice--error">{getApiErrorMessage(available.error)} <button className="hrms-outline-button" onClick={() => void available.refetch()}>Retry actions</button></div>}
      {error && <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}
    </li>
  );
}

export default function LeaveRequestsPage() {
  const [view, setView] = useState<View>('mine');
  const [data,setData]=useState<Record<string,unknown>>({});
  const [error, setError] = useState('');
  const queryClient = useQueryClient();
  const caps = useHrmsCapabilities();
  const noProfile = caps.data?.employee_profile === false;
  const key = ['hrms', 'leave', view];
  const list = useQuery({
    queryKey: key,
    queryFn: () => request<LeaveItem[]>(`/hrms/leave-requests?view=${view}&limit=100`),
    enabled: caps.isFetched && !noProfile,
  });
  const leaveForm=useFormSchema('HRMS.LeaveRequest',caps.isFetched&&!noProfile);
  const excluded=['employee_id','manager_id','identifier','hrms_operation_key'];
  const create = useMutation({
    mutationFn: () => request('/hrms/leave-requests', {
      method: 'POST',
      body: JSON.stringify({ ...commandValues(leaveForm.data?.fields??[],data,excluded), idempotency_key: createRequestId() }),
    }),
    onSuccess: () => {
      setError(''); setData({});
      void queryClient.invalidateQueries({ queryKey: ['hrms', 'leave'] });
    },
    onError: (cause) => setError(getApiErrorMessage(cause)),
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (String(data.end_date??'') < String(data.start_date??'')) { setError('End date must be on or after start date.'); return; }
    create.mutate();
  }

  if (noProfile) return <main className="hrms-workspace-page hrms-leave-page">
    <PageHero title="Leave requests" intro="Plan time away and keep your team in the loop." illustration="leave" />
    <p role="status" className="hrms-notice">Leave isn’t available for this account because it isn’t linked to an employee profile. Ask HR to link your account to your employee record.</p>
  </main>;

  return <main className="hrms-workspace-page hrms-leave-page">
    <PageHero title="Leave requests" intro="Plan time away and keep your team in the loop." illustration="leave"
      actions={<Link className="hrms-outline-button" to="/hrms/workflows">View workflows <ArrowRight size={16} /></Link>}
      stats={list.isSuccess ? [
        { label: view === 'mine' ? 'Your requests' : 'Team requests', value: list.data.length },
        { label: 'Pending', value: list.data.filter(item => item.state === 'pending').length, tone: 'attention' },
        { label: 'Approved', value: list.data.filter(item => item.state === 'approved').length, tone: 'positive' },
        { label: 'Days approved', value: list.data.filter(item => item.state === 'approved').reduce((days, item) => days + (item.days ?? Math.max(1, Math.round((Date.parse(item.end_date) - Date.parse(item.start_date)) / 86_400_000) + 1)), 0) },
      ] : undefined} />
    <div className="hrms-leave-layout"><section className="hrms-surface hrms-leave-compose" aria-label="Request leave">
    <ConfiguredForm entityType="HRMS.LeaveRequest"><form onSubmit={submit} className="hrms-people-form">
      <div className="hrms-panel-title"><span className="hrms-work-icon"><CalendarDays size={23} strokeWidth={1.25} /></span><div><h2>Request leave</h2><p>Choose your dates and share a reason.</p></div></div>
      <div className="grid gap-4 sm:grid-cols-2">
        <ConfiguredInputs values={data} onChange={setData} exclude={excluded}/>
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
