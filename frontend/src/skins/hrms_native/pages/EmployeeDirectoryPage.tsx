import { createRequestId } from '../requestId';
import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Users, Search } from 'lucide-react';
import { useHrmsCapabilities } from '../capabilities';
import { getApiErrorMessage, request } from '../../../core/services/api/client';
import { PageHero } from '../components/PageHero';
import { EditEmployeeSheet, ExitEmployeeSheet, type EditableEmployee } from './EmployeeChangeSheets';

interface Employee extends EditableEmployee {
  work_email: string;
  reports_to_name: string | null;
  role: string;
  on_notice: boolean;
  account_status: string;
  onboarding_state: string;
  can_setup_access: boolean;
  uses_google_sign_in: boolean;
}
interface Options { departments: string[]; designations: string[]; roles: string[] }
const labelForRole = (role: string) => ({
  hrms_employee: 'Employee', hrms_manager: 'Manager',
  hrms_project_manager: 'Project Manager', hrms_delivery_manager: 'Delivery Manager',
  hrms_hr_basic: 'HR - Basic', hrms_hr_full: 'HR - Full',
  hrms_office_admin: 'Office Admin', hrms_finance: 'Finance',
}[role] ?? role);

/** Active, active on notice, notice ended (exit still to complete) or offboarded. */
const exitStage = (employee: Employee) => employee.employment_status === 'offboarded' ? 'offboarded'
  : !employee.last_working_day || employee.employment_status !== 'active' ? 'none'
  : employee.on_notice ? 'notice' : 'due';
const statusLabel = (employee: Employee) => ({
  notice: `On notice · last day ${employee.last_working_day?.slice(0, 10)}`,
  due: `Notice ended ${employee.last_working_day?.slice(0, 10)}`,
}[exitStage(employee) as string] ?? employee.employment_status.replaceAll('_', ' '));
const STATUS_FILTERS: Record<string, (employee: Employee) => boolean> = {
  active: employee => employee.employment_status === 'active' && exitStage(employee) === 'none',
  on_notice: employee => ['notice', 'due'].includes(exitStage(employee)),
  offboarded: employee => employee.employment_status === 'offboarded',
};

export default function EmployeeDirectoryPage() {
  const caps = useHrmsCapabilities();
  if (caps.isLoading) return <p role="status">Loading directory access...</p>;
  if (caps.isError) return <div role="alert">Could not load access. <button onClick={() => void caps.refetch()}>Try again</button></div>;
  if (!caps.data?.capabilities.includes('employee:read')) return <p className="p-6">Org Directory is not available to your role.</p>;
  return <EmployeeDirectory />;
}

function EmployeeDirectory() {
  const { data: capabilities } = useHrmsCapabilities();
  const canCreate = capabilities?.capabilities.includes('employee:create') ?? false;
  const canExit = capabilities?.capabilities.includes('employee:exit') ?? false;
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [accessMessage, setAccessMessage] = useState('');
  const [editing, setEditing] = useState<Employee | null>(null);
  const [exiting, setExiting] = useState<Employee | null>(null);
  const employees = useQuery({
    queryKey: ['hrms', 'employees'],
    queryFn: () => request<Employee[]>('/hrms/employees'),
  });
  const options = useQuery({
    queryKey: ['hrms', 'employee-options'],
    queryFn: () => request<Options>('/hrms/employees/form-options'),
    enabled: canCreate && editing !== null,
  });
  const visible = useMemo(() => (employees.data ?? []).filter((employee) => {
    const matchesText = `${employee.full_name} ${employee.work_email} ${employee.employee_code}`
      .toLowerCase().includes(search.toLowerCase());
    return matchesText && (!status || STATUS_FILTERS[status](employee));
  }), [employees.data, search, status]);
  const setupAccess = useMutation({
    mutationFn: (employee: Employee) => request<{ message: string }>(`/hrms/employees/${employee.entity_id}/setup-access`, {
      method: 'POST', body: JSON.stringify({ idempotency_key: createRequestId() }),
    }),
    onSuccess: (result) => setAccessMessage(result.message),
    onError: (cause) => setAccessMessage(getApiErrorMessage(cause)),
    onSettled: () => void queryClient.invalidateQueries({ queryKey: ['hrms'] }),
  });
  const withdrawExit = useMutation({
    mutationFn: (employee: Employee) => request(`/hrms/employees/${employee.entity_id}/exit/withdraw`, {
      method: 'POST', body: JSON.stringify({ idempotency_key: createRequestId() }),
    }),
    onSuccess: (_, employee) => setAccessMessage(`${employee.full_name}'s exit was withdrawn; they stay on as before.`),
    onError: (cause) => setAccessMessage(getApiErrorMessage(cause)),
    onSettled: () => void queryClient.invalidateQueries({ queryKey: ['hrms'] }),
  });
  const changed = (message: string) => {
    setEditing(null); setExiting(null); setAccessMessage(message);
    void queryClient.invalidateQueries({ queryKey: ['hrms'] });
  };
  const input = 'hrms-field-input';

  return <main className="hrms-workspace-page hrms-people-page">
    <PageHero title="Org Directory" intro="Get to know the people behind our work." illustration="employees"
      stats={employees.isSuccess ? [
        { label: 'People', value: employees.data.length },
        { label: 'Active', value: employees.data.filter(employee => employee.employment_status === 'active').length, tone: 'positive' },
        { label: 'Departments', value: new Set(employees.data.map(employee => employee.department).filter(Boolean)).size },
        { label: 'On notice', value: employees.data.filter(STATUS_FILTERS.on_notice).length },
      ] : undefined} />
    {accessMessage && <div role={setupAccess.isError || withdrawExit.isError ? "alert" : "status"} className="hrms-notice">{accessMessage}</div>}
    <div className="hrms-filter-bar"><label className="hrms-search"><Search size={18} aria-hidden="true" /><input aria-label="Search employees" placeholder="Search by name, email or code…" value={search} onChange={(event) => setSearch(event.target.value)} className={input} /></label>
      <select aria-label="Employment status" value={status} onChange={(event) => setStatus(event.target.value)} className={input}>
        <option value="">All statuses</option><option value="active">Active</option><option value="on_notice">On notice</option><option value="offboarded">Offboarded</option>
      </select>
    </div>
    {employees.isLoading && <p role="status" className="hrms-surface hrms-work-feedback">Loading employees…</p>}
    {employees.isError && <div role="alert" className="hrms-notice hrms-notice--error"><p>{getApiErrorMessage(employees.error)}</p><button className="hrms-outline-button" onClick={() => void employees.refetch()}>Try again</button></div>}
    {employees.data && <div className="hrms-surface hrms-directory">
      <div className="hrms-directory-heading"><span className="hrms-work-icon"><Users size={22} strokeWidth={1.25} /></span><div><h2>Employee directory</h2><p>{visible.length} of {employees.data.length} employees</p></div></div><div className="hrms-table-scroll">
      <table className="hrms-people-table"><thead className="bg-slate-50 text-slate-600"><tr>
        {['Name', 'Code', 'Department', 'Designation', 'Reports To', 'Access role', 'Employment', 'Account access', 'Onboarding', ...(canCreate || canExit ? ['Actions'] : [])].map((heading) => <th key={heading} className="p-3">{heading}</th>)}
      </tr></thead><tbody>{visible.map((employee) => <tr key={employee.entity_id} className="border-t border-slate-100">
        <td className="p-3"><strong>{employee.full_name}</strong><span className="hrms-employee-email">{employee.work_email}</span></td><td className="p-3">{employee.employee_code}</td><td className="p-3">{employee.department}</td>
        <td className="p-3">{employee.designation}</td><td className="p-3">{employee.reports_to_name || '—'}</td>
        <td className="p-3">{labelForRole(employee.role)}</td><td className="p-3"><span className="hrms-status" data-state={exitStage(employee) === 'none' ? employee.employment_status : 'pending'}>{statusLabel(employee)}</span></td>
        <td className="p-3"><span>{(employee.account_status ?? 'not_linked').replaceAll('_', ' ')}</span>
          {employee.can_setup_access && <button type="button" className="hrms-text-link" disabled={setupAccess.isPending}
            onClick={() => { setAccessMessage(''); setupAccess.mutate(employee); }}>
            {setupAccess.isPending && setupAccess.variables?.entity_id === employee.entity_id ? 'Requesting…' : employee.uses_google_sign_in ? 'Enable Google sign-in' : employee.account_status === 'pending' ? 'Activate & send setup email' : 'Request setup email'}
          </button>}</td>
        <td className="p-3">{(employee.onboarding_state ?? 'not_started').replaceAll('_', ' ')}</td>
        {(canCreate || canExit) && <td className="p-3"><div className="flex flex-col items-start gap-1">{employee.employment_status !== 'offboarded' && <>
          {canCreate && <button type="button" className="hrms-text-link" onClick={() => { setAccessMessage(''); setEditing(employee); }}>Edit</button>}
          {canExit && exitStage(employee) === 'none' && <button type="button" className="hrms-text-link" onClick={() => { setAccessMessage(''); setExiting(employee); }}>Record exit</button>}
          {canExit && exitStage(employee) === 'due' && <button type="button" className="hrms-text-link" onClick={() => { setAccessMessage(''); setExiting(employee); }}>Complete exit</button>}
          {canExit && ['notice', 'due'].includes(exitStage(employee)) && <button type="button" className="hrms-text-link" disabled={withdrawExit.isPending}
            onClick={() => { setAccessMessage(''); withdrawExit.mutate(employee); }}>{withdrawExit.isPending && withdrawExit.variables?.entity_id === employee.entity_id ? 'Withdrawing…' : 'Withdraw exit'}</button>}
        </>}</div></td>}
      </tr>)}{visible.length === 0 && <tr><td colSpan={canCreate || canExit ? 10 : 9} className="hrms-empty-message">No employees match your filters.</td></tr>}</tbody></table></div>
    </div>}
    {editing && <EditEmployeeSheet key={editing.entity_id} employee={editing} employees={employees.data ?? []} options={options.data} onClose={() => setEditing(null)} onSaved={changed} />}
    {exiting && <ExitEmployeeSheet key={exiting.entity_id} employee={exiting} onClose={() => setExiting(null)} onSaved={changed} />}
  </main>;
}
