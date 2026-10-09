import { useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { getApiErrorMessage, request } from '../../../core/services/api/client';
import { ConfiguredField, ConfiguredForm } from '../forms/ConfiguredForm';
import { createRequestId } from '../requestId';

export interface EditableEmployee {
  entity_id: string;
  employee_code: string;
  full_name: string;
  department: string;
  designation: string;
  employment_status: string;
  reports_to_entity_id?: string | null;
  date_joined?: string | null;
  employment_type?: string | null;
  work_location?: string | null;
  notice_period_days?: number | null;
  phone?: string | null;
  last_working_day?: string | null;
  exit_reason?: string | null;
}
interface Options { departments: string[]; designations: string[] }

const input = 'hrms-field-input';
const today = () => new Date().toISOString().slice(0, 10);
const splitName = (fullName: string) => { const [first, ...rest] = fullName.trim().split(/\s+/); return [first ?? '', rest.join(' ')]; };
/** Offer the saved value even when it is no longer in the list, so editing other details keeps it. */
const withCurrent = (choices: string[] | undefined, current: string) => (choices ?? []).includes(current) || !current ? choices ?? [] : [current, ...(choices ?? [])];

/** HR corrects job and personal details. Work email, employee code and access role are not changed here. */
export function EditEmployeeSheet({ employee, employees, options, onClose, onSaved }: {
  employee: EditableEmployee; employees: EditableEmployee[]; options?: Options; onClose: () => void; onSaved: (message: string) => void;
}) {
  const [first, last] = splitName(employee.full_name);
  const [form, setForm] = useState({
    first_name: first, last_name: last, department: employee.department, designation: employee.designation,
    reports_to_entity_id: employee.reports_to_entity_id ?? '', date_joined: (employee.date_joined ?? today()).slice(0, 10),
    employment_type: employee.employment_type ?? 'full_time', work_location: employee.work_location ?? '',
    notice_period_days: employee.notice_period_days == null ? '' : String(employee.notice_period_days), phone: employee.phone ?? '',
  });
  const [key] = useState(() => createRequestId());
  const save = useMutation({
    mutationFn: () => request(`/hrms/employees/${employee.entity_id}`, {
      method: 'PUT',
      body: JSON.stringify({
        ...form, reports_to_entity_id: form.reports_to_entity_id || null,
        notice_period_days: form.notice_period_days ? Number(form.notice_period_days) : null,
        phone: form.phone || null, work_location: form.work_location || null, idempotency_key: key,
      }),
    }),
    onSuccess: () => onSaved(`${form.first_name} ${form.last_name}'s details were updated.`),
  });
  const set = (field: keyof typeof form) => (value: string) => setForm(current => ({ ...current, [field]: value }));
  const submit = (event: FormEvent) => { event.preventDefault(); save.mutate(); };
  const managers = employees.filter(item => item.employment_status === 'active' && item.entity_id !== employee.entity_id);

  return <Sheet open onOpenChange={open => { if (!open) onClose(); }}>
    <SheetContent className="hrms-brand hrms-employee-form overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-2xl">
      <SheetHeader><p className="hrms-eyebrow">{employee.employee_code}</p><SheetTitle>Edit employee</SheetTitle>
        <p className="hrms-form-intro">Correct job and personal details. Work email and employee code identify the account and stay as they are; access roles are managed with account access.</p></SheetHeader>
      <ConfiguredForm entityType="HRMS.Employee"><form onSubmit={submit} className="hrms-people-form">
        <fieldset disabled={save.isPending} className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <ConfiguredField field="first_name" label="First name" className="text-sm font-medium"><input required maxLength={100} value={form.first_name} onChange={e => set('first_name')(e.target.value)} className={input} /></ConfiguredField>
            <ConfiguredField field="last_name" label="Last name" className="text-sm font-medium"><input required maxLength={100} value={form.last_name} onChange={e => set('last_name')(e.target.value)} className={input} /></ConfiguredField>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <ConfiguredField field="department" label="Department" className="text-sm font-medium"><select required value={form.department} onChange={e => set('department')(e.target.value)} className={input}>{withCurrent(options?.departments, employee.department).map(item => <option key={item} value={item}>{item}</option>)}</select></ConfiguredField>
            <ConfiguredField field="designation" label="Designation" className="text-sm font-medium"><select required value={form.designation} onChange={e => set('designation')(e.target.value)} className={input}>{withCurrent(options?.designations, employee.designation).map(item => <option key={item} value={item}>{item}</option>)}</select></ConfiguredField>
          </div>
          <ConfiguredField field="reports_to_employee_code" label="Reporting manager" className="block text-sm font-medium"><select value={form.reports_to_entity_id} onChange={e => set('reports_to_entity_id')(e.target.value)} className={input}><option value="">None</option>{managers.map(item => <option key={item.entity_id} value={item.entity_id}>{item.full_name} · {item.designation}</option>)}</select></ConfiguredField>
          <div className="grid gap-3 sm:grid-cols-3">
            <ConfiguredField field="employment_type" label="Employment type" className="text-sm font-medium"><select value={form.employment_type} onChange={e => set('employment_type')(e.target.value)} className={input}><option value="full_time">Full time</option><option value="contract">Contract</option><option value="intern">Intern</option></select></ConfiguredField>
            <ConfiguredField field="date_joined" label="Date joined" className="text-sm font-medium"><input required type="date" value={form.date_joined} onChange={e => set('date_joined')(e.target.value)} className={input} /></ConfiguredField>
            <ConfiguredField field="notice_period_days" label="Notice period" className="text-sm font-medium"><input type="number" min={0} max={365} value={form.notice_period_days} onChange={e => set('notice_period_days')(e.target.value)} className={input} /></ConfiguredField>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <ConfiguredField field="phone" label="Phone" className="text-sm font-medium"><input maxLength={30} value={form.phone} onChange={e => set('phone')(e.target.value)} className={input} /></ConfiguredField>
            <ConfiguredField field="work_location" label="Work location" className="text-sm font-medium"><input maxLength={100} value={form.work_location} onChange={e => set('work_location')(e.target.value)} className={input} /></ConfiguredField>
          </div>
        </fieldset>
        {save.isError && <p role="alert" className="text-sm text-red-700">{getApiErrorMessage(save.error)}</p>}
        <div className="hrms-form-actions"><button type="button" onClick={onClose} className="hrms-outline-button">Cancel</button><button type="submit" disabled={save.isPending || !options} className="hrms-primary-button">{save.isPending ? 'Saving…' : 'Save changes'}</button></div>
      </form></ConfiguredForm>
    </SheetContent>
  </Sheet>;
}

const REASONS = [['resignation', 'Resignation'], ['termination', 'Termination'], ['contract_end', 'Contract ended'], ['retirement', 'Retirement'], ['other', 'Other']] as const;

/** Record that an employee is leaving. A future last day means notice; today or earlier offboards and signs them out. */
export function ExitEmployeeSheet({ employee, onClose, onSaved }: { employee: EditableEmployee; onClose: () => void; onSaved: (message: string) => void }) {
  // Completing a notice period starts from the day and reason already recorded.
  const [form, setForm] = useState({ last_working_day: (employee.last_working_day ?? today()).slice(0, 10), reason: employee.exit_reason ?? 'resignation', note: '' });
  const [key] = useState(() => createRequestId());
  const leavingNow = form.last_working_day <= today();
  const save = useMutation({
    mutationFn: () => request(`/hrms/employees/${employee.entity_id}/exit`, {
      method: 'POST', body: JSON.stringify({ ...form, note: form.note || null, idempotency_key: key }),
    }),
    onSuccess: () => onSaved(leavingNow ? `${employee.full_name} was offboarded and can no longer sign in.` : `${employee.full_name} is on notice until ${form.last_working_day}.`),
  });
  const submit = (event: FormEvent) => { event.preventDefault(); save.mutate(); };

  return <Sheet open onOpenChange={open => { if (!open) onClose(); }}>
    <SheetContent className="hrms-brand hrms-employee-form overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-xl">
      <SheetHeader><p className="hrms-eyebrow">{employee.employee_code}</p><SheetTitle>Record exit · {employee.full_name}</SheetTitle>
        <p className="hrms-form-intro">Set the last working day. A future date keeps them working while on notice; on or after it, they are offboarded and their sign-in is suspended. The record is kept.</p></SheetHeader>
      <form onSubmit={submit} className="hrms-people-form">
        <fieldset disabled={save.isPending} className="space-y-3">
          <label className="block space-y-1 text-sm font-medium"><span>Last working day</span><input required type="date" min={(employee.date_joined ?? '').slice(0, 10) || undefined} value={form.last_working_day} onChange={e => setForm({ ...form, last_working_day: e.target.value })} className={input} /></label>
          <label className="block space-y-1 text-sm font-medium"><span>Reason</span><select required value={form.reason} onChange={e => setForm({ ...form, reason: e.target.value })} className={input}>{REASONS.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>
          <label className="block space-y-1 text-sm font-medium"><span>Note</span><textarea maxLength={2000} rows={3} value={form.note} onChange={e => setForm({ ...form, note: e.target.value })} className={input} /></label>
        </fieldset>
        <p className={leavingNow ? 'hrms-notice hrms-notice--error' : 'hrms-notice'}>{leavingNow
          ? 'Saving offboards this employee now and suspends their sign-in.'
          : 'Saving puts this employee on notice. Record the exit again on their last day to offboard them.'}</p>
        {save.isError && <p role="alert" className="text-sm text-red-700">{getApiErrorMessage(save.error)}</p>}
        <div className="hrms-form-actions"><button type="button" onClick={onClose} className="hrms-outline-button">Cancel</button><button type="submit" disabled={save.isPending} className="hrms-primary-button">{save.isPending ? 'Saving…' : leavingNow ? 'Offboard employee' : 'Record notice'}</button></div>
      </form>
    </SheetContent>
  </Sheet>;
}
