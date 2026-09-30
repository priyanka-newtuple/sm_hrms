import { ConfiguredForm, ConfiguredField } from '../forms/ConfiguredForm';
import { useMemo, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Users, Search, ArrowRight } from 'lucide-react';
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
}
interface Options { departments: string[]; designations: string[]; roles: string[] }
interface CreatedEmployee {
  employee: Employee;
  onboarding_entity_id: string;
  onboarding_state: string;
  onboarding_task_count: number;
}

const labelForRole = (role: string) => ({
  hrms_employee: 'Employee', hrms_manager: 'Manager',
  hrms_hr_basic: 'HR - Basic', hrms_hr_full: 'HR - Full',
}[role] ?? role);

export default function EmployeeDirectoryPage() {
  const { data: capabilities } = useHrmsCapabilities();
  const canCreate = capabilities?.capabilities.includes('employee:create') ?? false;
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [created, setCreated] = useState<CreatedEmployee | null>(null);
  const [error, setError] = useState('');
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [form, setForm] = useState({
    first_name: '', last_name: '', work_email: '', department: '', designation: '',
    role: 'hrms_employee', reports_to_entity_id: '', date_joined: new Date().toISOString().slice(0, 10),
    employment_type: 'full_time', notice_period_days: '', phone: '', work_location: '',
  });
  const employees = useQuery({
    queryKey: ['hrms', 'employees'],
    queryFn: () => request<Employee[]>('/hrms/employees'),
  });
  const options = useQuery({
    queryKey: ['hrms', 'employee-options'],
    queryFn: () => request<Options>('/hrms/employees/form-options'),
    enabled: canCreate && showForm,
  });
  const visible = useMemo(() => (employees.data ?? []).filter((employee) => {
    const matchesText = `${employee.full_name} ${employee.work_email} ${employee.employee_code}`
      .toLowerCase().includes(search.toLowerCase());
    return matchesText && (!status || employee.employment_status === status);
  }), [employees.data, search, status]);
  const create = useMutation({
    mutationFn: () => request<CreatedEmployee>('/hrms/employees', {
      method: 'POST',
      body: JSON.stringify({
        ...form,
        reports_to_entity_id: form.reports_to_entity_id || null,
        notice_period_days: form.notice_period_days ? Number(form.notice_period_days) : null,
        phone: form.phone || null,
        work_location: form.work_location || null,
        idempotency_key: key,
      }),
    }),
    onSuccess: (result) => {
      setError(''); setShowForm(false); setKey(crypto.randomUUID());
      setCreated(result);
      void queryClient.invalidateQueries({ queryKey: ['hrms'] });
    },
    onError: (cause) => setError(getApiErrorMessage(cause)),
  });
  const set = (field: keyof typeof form) => (value: string) => setForm((current) => ({ ...current, [field]: value }));
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); create.mutate(); }
  const input = 'hrms-field-input';

  return <main className="hrms-workspace-page hrms-people-page">
    <header className="hrms-workspace-heading"><div><p className="hrms-eyebrow">OUR PEOPLE</p><h1>Employees</h1><p className="hrms-intro">Get to know the people behind our work.</p></div>
      {canCreate && <button type="button" onClick={() => { setCreated(null); setShowForm(true); }} className="hrms-primary-button"><Plus size={16} /> Add Employee</button>}
    </header>
    {created && <div role="status" className="hrms-notice">
      <strong>{created.employee.full_name} ({created.employee.employee_code}) was added.</strong>{' '}
      Onboarding is {created.onboarding_state.replaceAll('_', ' ')} with {created.onboarding_task_count} assigned tasks.
      {' '}<Link to={`/hrms/onboarding?case=${created.onboarding_entity_id}`} className="hrms-text-link">View onboarding steps <ArrowRight size={15} /></Link>
    </div>}
    <div className="hrms-filter-bar"><label className="hrms-search"><Search size={18} aria-hidden="true" /><input aria-label="Search employees" placeholder="Search by name, email or code…" value={search} onChange={(event) => setSearch(event.target.value)} className={input} /></label>
      <select aria-label="Employment status" value={status} onChange={(event) => setStatus(event.target.value)} className={input}>
        <option value="">All statuses</option><option value="active">Active</option><option value="on_leave">On leave</option><option value="offboarded">Offboarded</option>
      </select>
    </div>
    {employees.isLoading && <p role="status" className="hrms-surface hrms-work-feedback">Loading employees…</p>}
    {employees.isError && <div role="alert" className="hrms-notice hrms-notice--error"><p>{getApiErrorMessage(employees.error)}</p><button className="hrms-outline-button" onClick={() => void employees.refetch()}>Try again</button></div>}
    {employees.data && <div className="hrms-surface hrms-directory">
      <div className="hrms-directory-heading"><span className="hrms-work-icon"><Users size={22} strokeWidth={1.25} /></span><div><h2>Employee directory</h2><p>{visible.length} of {employees.data.length} employees</p></div></div><div className="hrms-table-scroll">
      <table className="hrms-people-table"><thead className="bg-slate-50 text-slate-600"><tr>
        {['Name', 'Code', 'Department', 'Designation', 'Reports To', 'Role', 'Status'].map((heading) => <th key={heading} className="p-3">{heading}</th>)}
      </tr></thead><tbody>{visible.map((employee) => <tr key={employee.entity_id} className="border-t border-slate-100">
        <td className="p-3"><strong>{employee.full_name}</strong><span className="hrms-employee-email">{employee.work_email}</span></td><td className="p-3">{employee.employee_code}</td><td className="p-3">{employee.department}</td>
        <td className="p-3">{employee.designation}</td><td className="p-3">{employee.reports_to_name || '—'}</td>
        <td className="p-3">{labelForRole(employee.role)}</td><td className="p-3"><span className="hrms-status" data-state={employee.employment_status}>{employee.employment_status.replaceAll('_', ' ')}</span></td>
      </tr>)}{visible.length === 0 && <tr><td colSpan={7} className="hrms-empty-message">No employees match your filters.</td></tr>}</tbody></table></div>
    </div>}
    <Sheet open={showForm} onOpenChange={setShowForm}>
      <SheetContent className="hrms-brand hrms-employee-form overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-2xl">
        <SheetHeader><p className="hrms-eyebrow">GROW THE TEAM</p><SheetTitle>Add Employee</SheetTitle><p className="hrms-form-intro">Create an employee profile and start their onboarding journey.</p></SheetHeader>
        {options.isLoading && <p role="status" className="hrms-work-feedback">Loading employee options…</p>}
        {options.isError && <div role="alert" className="hrms-notice hrms-notice--error">{getApiErrorMessage(options.error)}<button className="hrms-outline-button" onClick={() => void options.refetch()}>Try again</button></div>}
        <ConfiguredForm entityType="HRMS.Employee"><form onSubmit={submit} className="hrms-people-form">
          <div className="grid gap-3 sm:grid-cols-2">
            <ConfiguredField field="first_name" label="First name" className="text-sm font-medium"><input required maxLength={100} value={form.first_name} onChange={(e) => set('first_name')(e.target.value)} className={input} /></ConfiguredField>
            <ConfiguredField field="last_name" label="Last name" className="text-sm font-medium"><input required maxLength={100} value={form.last_name} onChange={(e) => set('last_name')(e.target.value)} className={input} /></ConfiguredField>
          </div>
          <ConfiguredField field="work_email" label="Work email" className="block text-sm font-medium"><input required type="email" placeholder="first.last@newtuple.com" value={form.work_email} onChange={(e) => set('work_email')(e.target.value)} className={input} /><span className="text-xs text-slate-500">Must be @newtuple.com to match Google SSO.</span></ConfiguredField>
          <div className="grid gap-3 sm:grid-cols-2">
            <ConfiguredField field="department" label="Department" className="text-sm font-medium"><select required value={form.department} onChange={(e) => set('department')(e.target.value)} className={input}><option value="">Select department…</option>{options.data?.departments.map((item) => <option key={item} value={item}>{item}</option>)}</select></ConfiguredField>
            <ConfiguredField field="designation" label="Designation" className="text-sm font-medium"><select required value={form.designation} onChange={(e) => set('designation')(e.target.value)} className={input}><option value="">Select designation…</option>{options.data?.designations.map((item) => <option key={item} value={item}>{item}</option>)}</select></ConfiguredField>
          </div>
          <ConfiguredField field="role" label="Role" className="block text-sm font-medium"><select required value={form.role} onChange={(e) => set('role')(e.target.value)} className={input}>{options.data?.roles.map((role) => <option key={role} value={role}>{labelForRole(role)}</option>)}</select></ConfiguredField>
          <ConfiguredField field="reports_to_employee_code" label="Reporting manager" className="block text-sm font-medium"><select value={form.reports_to_entity_id} onChange={(e) => set('reports_to_entity_id')(e.target.value)} className={input}><option value="">None</option>{employees.data?.filter((item) => item.employment_status === 'active').map((item) => <option key={item.entity_id} value={item.entity_id}>{item.full_name} — {item.designation}</option>)}</select></ConfiguredField>
          <div className="grid gap-3 sm:grid-cols-3">
            <ConfiguredField field="employment_type" label="Employment type" className="text-sm font-medium"><select value={form.employment_type} onChange={(e) => set('employment_type')(e.target.value)} className={input}><option value="full_time">Full time</option><option value="contract">Contract</option><option value="intern">Intern</option></select></ConfiguredField>
            <ConfiguredField field="date_joined" label="Date joined" className="text-sm font-medium"><input required type="date" value={form.date_joined} onChange={(e) => set('date_joined')(e.target.value)} className={input} /></ConfiguredField>
            <ConfiguredField field="notice_period_days" label="Notice period" className="text-sm font-medium"><input type="number" min={0} max={365} value={form.notice_period_days} onChange={(e) => set('notice_period_days')(e.target.value)} className={input} /></ConfiguredField>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <ConfiguredField field="phone" label="Phone" className="text-sm font-medium"><input maxLength={30} value={form.phone} onChange={(e) => set('phone')(e.target.value)} className={input} /></ConfiguredField>
            <ConfiguredField field="work_location" label="Work location" className="text-sm font-medium"><input maxLength={100} value={form.work_location} onChange={(e) => set('work_location')(e.target.value)} className={input} /></ConfiguredField>
          </div>
          {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
          <div className="hrms-form-actions"><button type="button" onClick={() => setShowForm(false)} className="hrms-outline-button">Cancel</button><button type="submit" disabled={create.isPending || !options.data} className="hrms-primary-button">{create.isPending ? 'Creating…' : 'Create employee'}</button></div>
        </form></ConfiguredForm>
      </SheetContent>
    </Sheet>
  </main>;
}
