import { CustomFields, type CustomValues } from '../forms/CustomFields';
import { createRequestId } from '../requestId';
import { ConfiguredForm, ConfiguredField } from '../forms/ConfiguredForm';
import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, ArrowRight } from 'lucide-react';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Link } from 'react-router-dom';
import { useHrmsCapabilities } from '../capabilities';
import { getApiErrorMessage, request } from '../../../core/services/api/client';

interface Employee {
  entity_id: string;
  employee_code: string;
  full_name: string;
  work_email: string;
  department: string;
  designation: string;
  reports_to_name: string | null;
  employment_status: string;
  role: string;
  account_status: string;
  onboarding_state: string;
  can_setup_access: boolean;
  uses_google_sign_in: boolean;
}
interface Options { departments: string[]; designations: string[]; department_labels?: Record<string, string>; designation_labels?: Record<string, string>; roles: string[]; role_labels: Record<string, string> }
interface CreatedEmployee {
  employee: Employee;
  onboarding_entity_id: string;
  onboarding_state: string;
  onboarding_task_count: number;
}

export default function AddEmployee() {
  const { data: capabilities } = useHrmsCapabilities();
  const canCreate = capabilities?.capabilities.includes('employee:create') ?? false;
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [created, setCreated] = useState<CreatedEmployee | null>(null);
  const [error, setError] = useState('');
  const [custom, setCustom] = useState<CustomValues>({});
  const [key, setKey] = useState(() => createRequestId());
  const [form, setForm] = useState({
    first_name: '', last_name: '', work_email: '', department: '', designation: '',
    role: '', reports_to_entity_id: '', date_joined: new Date().toISOString().slice(0, 10),
    employment_type: 'full_time', notice_period_days: '', phone: '', work_location: '',
  });
  const employees = useQuery({
    queryKey: ['hrms', 'employees'],
    queryFn: () => request<Employee[]>('/hrms/employees'),
    enabled: canCreate && showForm,
  });
  const options = useQuery({
    queryKey: ['hrms', 'employee-options'],
    queryFn: () => request<Options>('/hrms/employees/form-options'),
    enabled: canCreate && showForm,
  });
  const create = useMutation({
    mutationFn: () => request<CreatedEmployee>('/hrms/employees', {
      method: 'POST',
      body: JSON.stringify({
        ...form,
        custom,
        reports_to_entity_id: form.reports_to_entity_id || null,
        notice_period_days: form.notice_period_days ? Number(form.notice_period_days) : null,
        phone: form.phone || null,
        work_location: form.work_location || null,
        idempotency_key: key,
      }),
    }),
    onSuccess: (result) => {
      setError(''); setShowForm(false); setKey(createRequestId());
      setCreated(result); setCustom({});
      void queryClient.invalidateQueries({ queryKey: ['hrms'] });
    },
    onError: (cause) => setError(getApiErrorMessage(cause)),
  });
  const set = (field: keyof typeof form) => (value: string) => setForm((current) => ({ ...current, [field]: value }));
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); create.mutate(); }
  const input = 'hrms-field-input';

  if (!canCreate) return null;
  return <>
    <button type="button" className="hrms-primary-button" onClick={() => { setCreated(null); setShowForm(true); }}><Plus size={16} /> Add employee / Start onboarding</button>
    {created && <div role="status" className="hrms-notice">
      <strong>{created.employee.full_name} ({created.employee.employee_code}) was added.</strong>{' '}
      Onboarding is {created.onboarding_state.replaceAll('_', ' ')} with {created.onboarding_task_count} assigned tasks.
      {' '}New accounts await Super Admin approval in Settings → Users and appear in their My Tasks.
      {' '}<Link to={`/hrms/cockpit?area=onboarding&case=${created.onboarding_entity_id}`} className="hrms-text-link">View onboarding steps <ArrowRight size={15} /></Link>
    </div>}
    <Sheet open={showForm} onOpenChange={setShowForm}>
      <SheetContent className="hrms-brand hrms-employee-form overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-2xl">
        <SheetHeader><p className="hrms-eyebrow">GROW THE TEAM</p><SheetTitle>Add Employee</SheetTitle><p className="hrms-form-intro">Create an employee profile, link their account, and start onboarding. All new accounts require Super Admin approval before sign-in.</p></SheetHeader>
        {options.isLoading && <p role="status" className="hrms-work-feedback">Loading employee options…</p>}
        {options.isError && <div role="alert" className="hrms-notice hrms-notice--error">{getApiErrorMessage(options.error)}<button className="hrms-outline-button" onClick={() => void options.refetch()}>Try again</button></div>}
        <ConfiguredForm entityType="HRMS.Employee"><form onSubmit={submit} className="hrms-people-form">
          <div className="grid gap-3 sm:grid-cols-2">
            <ConfiguredField field="first_name" label="First name" className="text-sm font-medium"><input required maxLength={100} value={form.first_name} onChange={(e) => set('first_name')(e.target.value)} className={input} /></ConfiguredField>
            <ConfiguredField field="last_name" label="Last name" className="text-sm font-medium"><input required maxLength={100} value={form.last_name} onChange={(e) => set('last_name')(e.target.value)} className={input} /></ConfiguredField>
          </div>
          <ConfiguredField field="work_email" label="Work email" className="block text-sm font-medium"><input required type="email" placeholder="first.last@newtuple.com" value={form.work_email} onChange={(e) => set('work_email')(e.target.value)} className={input} /><span className="text-xs text-slate-500">Must be @newtuple.com to match Google SSO.</span></ConfiguredField>
          <div className="grid gap-3 sm:grid-cols-2">
            <ConfiguredField field="department" label="Department" className="text-sm font-medium"><select required value={form.department} onChange={(e) => set('department')(e.target.value)} className={input}><option value="">Select department…</option>{options.data?.departments.map((item) => <option key={item} value={item}>{options.data?.department_labels?.[item] ?? item}</option>)}</select></ConfiguredField>
            <ConfiguredField field="designation" label="Designation" className="text-sm font-medium"><select required value={form.designation} onChange={(e) => set('designation')(e.target.value)} className={input}><option value="">Select designation…</option>{options.data?.designations.map((item) => <option key={item} value={item}>{options.data?.designation_labels?.[item] ?? item}</option>)}</select></ConfiguredField>
          </div>
          <ConfiguredField field="role" label="Access role" className="block text-sm font-medium"><select required value={form.role} onChange={(e) => set('role')(e.target.value)} className={input}><option value="">Select a role…</option>{options.data?.roles.map((role) => <option key={role} value={role}>{options.data?.role_labels?.[role] ?? role}</option>)}</select></ConfiguredField>
          <ConfiguredField field="reports_to_employee_code" label="Reporting manager" className="block text-sm font-medium"><select value={form.reports_to_entity_id} onChange={(e) => set('reports_to_entity_id')(e.target.value)} className={input}><option value="">None</option>{employees.data?.filter((item) => item.employment_status === 'active').map((item) => <option key={item.entity_id} value={item.entity_id}>{item.full_name} · {item.designation}</option>)}</select></ConfiguredField>
          <div className="grid gap-3 sm:grid-cols-3">
            <ConfiguredField field="employment_type" label="Employment type" className="text-sm font-medium"><select value={form.employment_type} onChange={(e) => set('employment_type')(e.target.value)} className={input}><option value="full_time">Full time</option><option value="contract">Contract</option><option value="intern">Intern</option></select></ConfiguredField>
            <ConfiguredField field="date_joined" label="Date joined" className="text-sm font-medium"><input required type="date" value={form.date_joined} onChange={(e) => set('date_joined')(e.target.value)} className={input} /></ConfiguredField>
            <ConfiguredField field="notice_period_days" label="Notice period" className="text-sm font-medium"><input type="number" min={0} max={365} value={form.notice_period_days} onChange={(e) => set('notice_period_days')(e.target.value)} className={input} /></ConfiguredField>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <ConfiguredField field="phone" label="Phone" className="text-sm font-medium"><input maxLength={30} value={form.phone} onChange={(e) => set('phone')(e.target.value)} className={input} /></ConfiguredField>
            <ConfiguredField field="work_location" label="Work location" className="text-sm font-medium"><input maxLength={100} value={form.work_location} onChange={(e) => set('work_location')(e.target.value)} className={input} /></ConfiguredField>
          </div>
          <CustomFields entityType="HRMS.Employee" values={custom} onChange={setCustom} />
          {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
          <div className="hrms-form-actions"><button type="button" onClick={() => setShowForm(false)} className="hrms-outline-button">Cancel</button><button type="submit" disabled={create.isPending || !options.data} className="hrms-primary-button">{create.isPending ? 'Creating…' : 'Create employee & start onboarding'}</button></div>
        </form></ConfiguredForm>
      </SheetContent>
    </Sheet>
  </>;
}
