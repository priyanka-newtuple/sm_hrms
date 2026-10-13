import { useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { getApiErrorMessage, request } from '../../../core/services/api/client';
import { ConfiguredInputs, ConfiguredForm, useFormSchema, commandValues, employeeSystemFields, employeeAdapters, formValues } from '../forms/ConfiguredForm';
import { createRequestId } from '../requestId';
import { type CustomValues } from '../forms/CustomFields';

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
  custom?: CustomValues;
}
interface Options { departments: string[]; designations: string[]; department_labels?: Record<string, string>; designation_labels?: Record<string, string> }

const today = () => new Date().toISOString().slice(0, 10);
const splitName = (fullName: string) => { const [first, ...rest] = fullName.trim().split(/\s+/); return [first ?? '', rest.join(' ')]; };
/** HR corrects job and personal details. Work email, employee code and access role are not changed here. */
export function EditEmployeeSheet({ employee, employees, options, onClose, onSaved }: {
  employee: EditableEmployee; employees: EditableEmployee[]; options?: Options; onClose: () => void; onSaved: (message: string) => void;
}) {
  const [first, last] = splitName(employee.full_name);
  const [form, setForm] = useState<Record<string,unknown>>({
    ...employee.custom, first_name: first, last_name: last, department: employee.department, designation: employee.designation,
    reports_to_entity_id: employee.reports_to_entity_id ?? '', date_joined: (employee.date_joined ?? '').slice(0, 10),  // never guess a joining date
    employment_type: employee.employment_type ?? 'full_time', work_location: employee.work_location ?? '',
    notice_period_days: employee.notice_period_days == null ? '' : String(employee.notice_period_days), phone: employee.phone ?? '',
  });
  const [key] = useState(() => createRequestId());
  const schema=useFormSchema('HRMS.Employee');
  const excluded=[...employeeSystemFields,'work_email','hrms_role'];
  const save = useMutation({
    mutationFn: () => request(`/hrms/employees/${employee.entity_id}`, {
      method: 'PUT',
      body: JSON.stringify({
        ...commandValues(schema.data?.fields??[],form,excluded,employeeAdapters), idempotency_key:key,
      }),
    }),
    onSuccess: () => onSaved(`${form.first_name} ${form.last_name}'s details were updated.`),
  });
  const submit = (event: FormEvent) => { event.preventDefault(); save.mutate(); };
  const managers = employees.filter(item => item.employment_status === 'active' && item.entity_id !== employee.entity_id);

  return <Sheet open onOpenChange={open => { if (!open) onClose(); }}>
    <SheetContent className="hrms-brand hrms-employee-form overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-2xl">
      <SheetHeader><p className="hrms-eyebrow">{employee.employee_code}</p><SheetTitle>Edit employee</SheetTitle>
        <p className="hrms-form-intro">Correct job and personal details. Work email and employee code identify the account and stay as they are; access roles are managed with account access.</p></SheetHeader>
      <ConfiguredForm entityType="HRMS.Employee"><form onSubmit={submit} className="hrms-people-form">
        <fieldset disabled={save.isPending} className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2"><ConfiguredInputs values={form} onChange={setForm} exclude={excluded} adapters={{...employeeAdapters,reports_to_employee_code:{...employeeAdapters.reports_to_employee_code,options:managers.map(e=>({id:e.entity_id,name:e.full_name}))}}}/></div>
        </fieldset>
        {save.isError && <p role="alert" className="text-sm text-red-700">{getApiErrorMessage(save.error)}</p>}
        <div className="hrms-form-actions"><button type="button" onClick={onClose} className="hrms-outline-button">Cancel</button><button type="submit" disabled={save.isPending || !options} className="hrms-primary-button">{save.isPending ? 'Saving…' : 'Save changes'}</button></div>
      </form></ConfiguredForm>
    </SheetContent>
  </Sheet>;
}

/** Record that an employee is leaving. A future last day means notice; today or earlier offboards and signs them out. */
export function ExitEmployeeSheet({ employee, onClose, onSaved }: { employee: EditableEmployee; onClose: () => void; onSaved: (message: string) => void }) {
  // Completing a notice period starts from the day and reason already recorded.
  const [form, setForm] = useState({ last_working_day: (employee.last_working_day ?? today()).slice(0, 10), reason: employee.exit_reason ?? 'resignation', note: '' });
  const [key] = useState(() => createRequestId());
  const schema=useFormSchema('HRMS.Employee');
  const exitFields=(schema.data?.fields??[]).filter(f=>['last_working_day','exit_reason','exit_note'].includes(f.field));
  const exitAdapters={exit_reason:{key:'reason'},exit_note:{key:'note'}};
  const leavingNow = form.reason === 'did_not_join' || form.last_working_day <= today();
  const save = useMutation({
    mutationFn: () => request(`/hrms/employees/${employee.entity_id}/exit`, {
      method: 'POST', body: JSON.stringify({ ...formValues(exitFields,form,[],exitAdapters), idempotency_key: key }),
    }),
    onSuccess: () => onSaved(leavingNow ? `${employee.full_name} was offboarded and can no longer sign in.` : `${employee.full_name} is on notice until ${form.last_working_day}.`),
  });
  const submit = (event: FormEvent) => { event.preventDefault(); save.mutate(); };

  return <Sheet open onOpenChange={open => { if (!open) onClose(); }}>
    <SheetContent className="hrms-brand hrms-employee-form overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-xl">
      <SheetHeader><p className="hrms-eyebrow">{employee.employee_code}</p><SheetTitle>Record exit · {employee.full_name}</SheetTitle>
        <p className="hrms-form-intro">Set the last working day. A future date keeps them working while on notice; on or after it, they are offboarded and their sign-in is suspended. The record is kept.</p></SheetHeader>
      <ConfiguredForm entityType="HRMS.Employee"><form onSubmit={submit} className="hrms-people-form">
        <fieldset disabled={save.isPending} className="space-y-3">
          <ConfiguredInputs fields={exitFields} values={form} onChange={v=>setForm(v as typeof form)} adapters={exitAdapters}/>
        </fieldset>
        <p className={leavingNow ? 'hrms-notice hrms-notice--error' : 'hrms-notice'}>{leavingNow
          ? 'Saving offboards this employee now and suspends their sign-in.'
          : 'Saving puts this employee on notice. Record the exit again on their last day to offboard them.'}</p>
        {save.isError && <p role="alert" className="text-sm text-red-700">{getApiErrorMessage(save.error)}</p>}
        <div className="hrms-form-actions"><button type="button" onClick={onClose} className="hrms-outline-button">Cancel</button><button type="submit" disabled={save.isPending} className="hrms-primary-button">{save.isPending ? 'Saving…' : leavingNow ? 'Offboard employee' : 'Record notice'}</button></div>
      </form></ConfiguredForm>
    </SheetContent>
  </Sheet>;
}
