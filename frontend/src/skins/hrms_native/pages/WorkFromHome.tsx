import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Home, ChevronLeft, ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { request, getApiErrorMessage } from '@/core/services/api/client';
import { useHrmsCapabilities } from '../capabilities';
import { createRequestId } from '../requestId';
import { ConfiguredField, ConfiguredForm } from '../forms/ConfiguredForm';
import { WorkPanel } from '../components/WorkPanel';

type Policy = { year: number; annual_days: number; notice_days: number; revision: number };
export type Booking = { entity_id: string; employee_name: string; dates: string[]; reason: string; state: string; state_label: string; actions: string[]; is_mine: boolean; workflow_configuration: { transitions: { trigger: string; label: string; from_state: string }[] } };
export type WfhBoard = { policy: Policy | null; requests: Booking[]; calendar: { employee_id: string; employee_name: string; department: string; dates: string[] }[]; can_configure: boolean; can_approve: boolean; can_request: boolean; balance: { used: number; upcoming: number; pending: number; remaining: number } };
const localDate = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

export function useWfh(year = new Date().getFullYear()) {
  const caps = useHrmsCapabilities();
  return useQuery({ queryKey: ['hrms', 'wfh', year], queryFn: () => request<WfhBoard>(`/hrms/wfh?year=${year}`), enabled: caps.data?.capabilities.includes('wfh:view') ?? false });
}

export function useWfhInbox() {
  const caps = useHrmsCapabilities();
  return useQuery({ queryKey: ['hrms', 'wfh-inbox'], queryFn: () => request<Booking[]>('/hrms/wfh/inbox'), enabled: caps.data?.capabilities.includes('wfh:approve') ?? false });
}

function useCommand(path: string, done?: () => void) {
  const client = useQueryClient();
  const [pending, setPending] = useState<Record<string, unknown> | null>(null);
  const mutation = useMutation({ mutationFn: (body: Record<string, unknown>) => request(path, { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: async () => { setPending(null); done?.(); await client.invalidateQueries({ queryKey: ['hrms'] }); } });
  return { mutation, pending, submit: (data: Record<string, unknown>) => { const body = pending ?? { ...data, idempotency_key: createRequestId() }; setPending(body); mutation.mutate(body); },
    feedback: mutation.isError ? <div role="alert" className="hrms-notice hrms-notice--error">{getApiErrorMessage(mutation.error)} <button type="button" className="hrms-outline-button" onClick={() => pending && mutation.mutate(pending)}>Retry same request</button>{Number((mutation.error as {status?:number})?.status) < 500 && <button type="button" className="hrms-outline-button" onClick={() => { setPending(null); mutation.reset(); }}>Edit request</button>}</div> : null };
}

function PolicyEditor({ policy, year }: { policy: Policy | null; year: number }) {
  const [annual, setAnnual] = useState(policy?.annual_days ?? 0);
  const [notice, setNotice] = useState(policy?.notice_days ?? 0);
  const command = useCommand('/hrms/wfh/policy');
  return <section className="hrms-surface p-6"><h2 className="hrms-section-heading">Annual WFH policy · {year}</h2><p className="hrms-muted mb-4">Full-day requests go to HR Full or Super Admin for approval. HR cannot approve their own request. Weekends and published holidays are excluded; no carry-forward.</p>
    <ConfiguredForm entityType="HRMS.WorkFromHomePolicy"><form onSubmit={e => { e.preventDefault(); command.submit({ year, annual_days: annual, notice_days: notice, revision: policy?.revision ?? 0 }); }}>
      <fieldset disabled={command.pending !== null || year < new Date().getFullYear()} className="grid gap-4 sm:grid-cols-2">
        <ConfiguredField field="annual_days" label="Annual allowance (days)"><input className="hrms-field-input" type="number" min={0} max={366} required value={annual} onChange={e => setAnnual(Number(e.target.value))} /></ConfiguredField>
        <ConfiguredField field="notice_days" label="Minimum notice (calendar days)"><input className="hrms-field-input" type="number" min={0} max={365} required value={notice} onChange={e => setNotice(Number(e.target.value))} /></ConfiguredField>
        <div><button className="hrms-primary-button" type="submit">Save policy</button></div>
      </fieldset>{command.feedback}{command.mutation.isSuccess && <p role="status">Policy saved.</p>}
    </form></ConfiguredForm>
    <p className="hrms-muted mt-4">Pending requests reserve allowance. The annual limit cannot be reduced below existing pending and approved bookings. Changes to notice apply to new requests.</p>
  </section>;
}

export function WfhRequestRow({ item }: { item: Booking }) {
  const command = useCommand(`/hrms/wfh/requests/${item.entity_id}/actions`);
  return <li className="hrms-work-item"><h3>{item.employee_name}</h3><p>{item.dates.join(', ')}</p><span className="hrms-status" data-state={item.state}>{item.state_label}</span>{item.reason && <p>{item.reason}</p>}
    <div className="hrms-heading-actions">{item.actions.map(trigger => <button type="button" key={trigger} className="hrms-outline-button" disabled={command.pending !== null} onClick={() => command.submit({ trigger })}>{item.workflow_configuration.transitions.find(t => t.trigger === trigger && t.from_state === item.state)?.label ?? trigger}</button>)}</div>{command.feedback}
  </li>;
}

export function WorkFromHome({ cockpit = false }: { cockpit?: boolean }) {
  const caps = useHrmsCapabilities();
  const [month, setMonth] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));
  const [tab, setTab] = useState(cockpit ? 'requests' : 'calendar');
  const [selected, setSelected] = useState<string[]>([]);
  const [reason, setReason] = useState('');
  const [search, setSearch] = useState('');
  const year = month.getFullYear();
  const query = useWfh(year);
  const command = useCommand('/hrms/wfh/requests', () => { setSelected([]); setReason(''); setTab('requests'); });
  const board = query.data;
  const visibleRequests = board?.requests.filter(r => cockpit || r.is_mine) ?? [];
  function changeMonth(delta: number) { setMonth(d => new Date(d.getFullYear(), d.getMonth() + delta, 1)); setSelected([]); }
  const prefix = localDate(month).slice(0, 7);
  const count = new Date(year, month.getMonth() + 1, 0).getDate();
  const offset = (month.getDay() + 6) % 7;
  if (caps.isLoading) return <p role="status">Loading WFH access…</p>;
  if (caps.isError) return <p role="alert">Could not load WFH access. <button onClick={() => void caps.refetch()}>Try again</button></p>;
  if (!caps.data?.capabilities.includes('wfh:view')) return <p>Work from home is not available to your role.</p>;
  return <section className="hrms-wfh" aria-label="Work from home">
    <header className="hrms-directory-heading"><Home size={24} /><div><h2>Work from home</h2><p>Plan your days and see who is working remotely.</p></div></header>
    <nav className="hrms-content-categories" aria-label="WFH views"><button type="button" aria-pressed={tab === 'calendar'} onClick={() => setTab('calendar')}>Calendar</button><button type="button" aria-pressed={tab === 'requests'} onClick={() => setTab('requests')}>{cockpit ? 'Requests & approvals' : 'My requests'}</button>{cockpit && board?.can_configure && <button type="button" aria-pressed={tab === 'policy'} onClick={() => setTab('policy')}>Policy</button>}</nav>
    <div className="hrms-filter-bar"><button type="button" className="hrms-outline-button" aria-label="Previous month" disabled={command.pending !== null || year <= 2000} onClick={() => changeMonth(-1)}><ChevronLeft size={18} /></button><strong>{month.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}</strong><button type="button" className="hrms-outline-button" aria-label="Next month" disabled={command.pending !== null || year >= 2100} onClick={() => changeMonth(1)}><ChevronRight size={18} /></button></div>
    {query.isLoading && <p role="status">Loading work from home…</p>}
    {query.isError && <div role="alert" className="hrms-notice hrms-notice--error">{getApiErrorMessage(query.error)} <button className="hrms-outline-button" onClick={() => void query.refetch()}>Try again</button></div>}
    {board && <>
      {!board.policy && <p className="hrms-notice">HR has not configured a WFH policy for {year} yet.</p>}
      {board.can_request && board.policy && <p className="hrms-notice">{board.policy.annual_days} days allowed · {board.balance.used} used · {board.balance.upcoming} upcoming · {board.balance.pending} pending · <strong>{board.balance.remaining} remaining</strong></p>}
      {tab === 'policy' && cockpit && board.can_configure && <PolicyEditor key={`${year}-${board.policy?.revision ?? 0}`} policy={board.policy} year={year} />}
      {tab === 'requests' && <section className="hrms-surface p-6"><h2 className="hrms-section-heading">{cockpit ? 'Requests & approvals' : 'My requests'} · {year}</h2><p className="hrms-muted">HR reviews requests here. Pending dates are private and reserve allowance.</p><ul>{visibleRequests.map(r => <WfhRequestRow key={r.entity_id} item={r} />)}</ul>{visibleRequests.length === 0 && <p className="hrms-work-empty">No WFH requests for this year.</p>}</section>}
      {tab === 'calendar' && <>
        <label className="block mb-4">Search employees or departments<input className="hrms-field-input" value={search} onChange={e => setSearch(e.target.value)} /></label>
        <p className="hrms-muted mb-4">Approved WFH dates are visible to everyone in your organization. An empty day does not confirm office attendance.</p>
        <div className="hrms-wfh-calendar" role="group" aria-label="Work location calendar">{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(d => <div className="hrms-wfh-weekday" key={d}>{d}</div>)}{Array.from({length: offset}, (_, i) => <div key={`pad-${i}`} />)}{Array.from({length: count}, (_, i) => {
          const day = `${prefix}-${String(i + 1).padStart(2, '0')}`;
          const weekday = new Date(year, month.getMonth(), i + 1).getDay();
          const people = board.calendar.filter(p => p.dates.includes(day) && `${p.employee_name} ${p.department}`.toLowerCase().includes(search.toLowerCase()));
          return <div className="hrms-wfh-day" key={day} data-selected={selected.includes(day)}><button type="button" aria-label={`Request WFH ${day}`} aria-pressed={selected.includes(day)} disabled={!board.can_request || !board.policy || day < localDate(new Date()) || weekday === 0 || weekday === 6 || command.pending !== null} onClick={() => setSelected(s => s.includes(day) ? s.filter(d => d !== day) : [...s, day].sort())}>{i + 1}</button><ul>{people.map(p => <li key={p.employee_id}>{p.employee_name}</li>)}</ul></div>;
        })}</div>
        {board.can_request && board.policy && <ConfiguredForm entityType="HRMS.WorkFromHomeRequest"><form className="hrms-surface p-6 mt-4" onSubmit={e => { e.preventDefault(); command.submit({ dates: selected, reason }); }}>
          <h3 className="hrms-section-heading">Request work from home</h3><p>Select weekdays in the calendar above. Requests go to HR for approval.</p><p className="my-3">{selected.length ? selected.join(', ') : 'No dates selected'}</p>
          <fieldset disabled={command.pending !== null}><ConfiguredField field="reason" label="Note for HR (optional)"><textarea className="hrms-field-input" maxLength={2000} value={reason} onChange={e => setReason(e.target.value)} /></ConfiguredField><button className="hrms-primary-button mt-4" disabled={!selected.length} type="submit">Submit to HR</button></fieldset>{command.feedback}
        </form></ConfiguredForm>}
        {!board.can_request && <p className="hrms-notice">An active employee profile linked to your account is needed to request WFH.</p>}
      </>}
    </>}
  </section>;
}

export function WfhInbox() {
  const caps = useHrmsCapabilities();
  const query = useWfhInbox();
  if (!caps.data?.capabilities.includes('wfh:approve')) return null;
  const rows = query.data ?? [];
  return <WorkPanel title="Work from home approvals" description="Review employee work location requests." icon={Home} count={rows.length} loading={query.isLoading} error={query.isError ? getApiErrorMessage(query.error) : undefined} retry={() => void query.refetch()} empty="No WFH requests are waiting for you."><ul>{rows.map(r => <WfhRequestRow key={r.entity_id} item={r} />)}</ul><Link className="hrms-text-link" to="/hrms/cockpit?area=wfh">Open HR Cockpit</Link></WorkPanel>;
}
