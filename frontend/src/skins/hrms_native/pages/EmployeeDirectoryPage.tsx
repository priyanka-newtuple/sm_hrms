import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Users, Search } from 'lucide-react';
import { useHrmsCapabilities } from '../capabilities';
import { getApiErrorMessage, request } from '../../../core/services/api/client';
import { PageHero } from '../components/PageHero';
import type { EditableEmployee } from './EmployeeChangeSheets';

interface Employee extends EditableEmployee {
  work_email: string;
  role: string;
  on_notice: boolean;
}
const labelForRole = (role: string) => ({
  hrms_employee: 'Employee', hrms_manager: 'Manager',
  hrms_project_manager: 'Project Manager', hrms_delivery_manager: 'Delivery Manager',
  hrms_hr_basic: 'HR - Basic', hrms_hr_full: 'HR - Full',
  hrms_office_admin: 'Office Admin', hrms_finance: 'Finance',
}[role] ?? role);

const joiningDate = (value?: string | null) => {
  if (!value) return '—';
  const date = new Date(`${value.slice(0, 10)}T00:00:00`);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
};
const skillsLabel = (value: unknown) => Array.isArray(value)
  ? value.filter(item => typeof item === 'string' && item.trim()).join(', ') || '—'
  : typeof value === 'string' && value.trim() ? value : '—';

// Keep stored exit values compatible with access rules; show Inactive in the directory.
const isInactive = (employee: Employee) => ['offboarded', 'inactive'].includes(employee.employment_status);
const exitStage = (employee: Employee) => isInactive(employee) ? 'inactive'
  : !employee.last_working_day || employee.employment_status !== 'active' ? 'none'
  : employee.on_notice ? 'notice' : 'due';
const statusLabel = (employee: Employee) => ({
  inactive: 'Inactive',
  notice: `On notice · last day ${employee.last_working_day?.slice(0, 10)}`,
  due: `Notice ended ${employee.last_working_day?.slice(0, 10)}`,
}[exitStage(employee) as string] ?? (employee.employment_status === 'active' ? 'Active' : employee.employment_status.replaceAll('_', ' ')));
const STATUS_FILTERS: Record<string, (employee: Employee) => boolean> = {
  active: employee => employee.employment_status === 'active' && exitStage(employee) === 'none',
  on_notice: employee => ['notice', 'due'].includes(exitStage(employee)),
  inactive: isInactive,
};

export default function EmployeeDirectoryPage() {
  const caps = useHrmsCapabilities();
  if (caps.isLoading) return <p role="status">Loading directory access...</p>;
  if (caps.isError) return <div role="alert">Could not load access. <button onClick={() => void caps.refetch()}>Try again</button></div>;
  if (!caps.data?.capabilities.includes('employee:read')) return <p className="p-6">Org Directory is not available to your role.</p>;
  return <EmployeeDirectory />;
}

function EmployeeDirectory() {
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const employees = useQuery({
    queryKey: ['hrms', 'employees'],
    queryFn: () => request<Employee[]>('/hrms/employees'),
  });
  const visible = useMemo(() => (employees.data ?? []).filter((employee) => {
    const matchesText = `${employee.full_name} ${employee.work_email} ${employee.employee_code}`
      .toLowerCase().includes(search.toLowerCase());
    return matchesText && (!status || STATUS_FILTERS[status](employee));
  }), [employees.data, search, status]);
  const input = 'hrms-field-input';

  return <main className="hrms-workspace-page hrms-people-page">
    <PageHero title="Org Directory" intro="Get to know the people behind our work." illustration="employees"
      stats={employees.isSuccess ? [
        { label: 'People', value: employees.data.length },
        { label: 'Active', value: employees.data.filter(employee => employee.employment_status === 'active').length, tone: 'positive' },
        { label: 'Departments', value: new Set(employees.data.map(employee => employee.department).filter(Boolean)).size },
        { label: 'On notice', value: employees.data.filter(STATUS_FILTERS.on_notice).length },
      ] : undefined} />
    <div className="hrms-filter-bar"><label className="hrms-search"><Search size={18} aria-hidden="true" /><input aria-label="Search employees" placeholder="Search by name, email or code…" value={search} onChange={(event) => setSearch(event.target.value)} className={input} /></label>
      <select aria-label="Employment status" value={status} onChange={(event) => setStatus(event.target.value)} className={input}>
        <option value="">All statuses</option><option value="active">Active</option><option value="on_notice">On notice</option><option value="inactive">Inactive</option>
      </select>
    </div>
    {employees.isLoading && <p role="status" className="hrms-surface hrms-work-feedback">Loading employees…</p>}
    {employees.isError && <div role="alert" className="hrms-notice hrms-notice--error"><p>{getApiErrorMessage(employees.error)}</p><button className="hrms-outline-button" onClick={() => void employees.refetch()}>Try again</button></div>}
    {employees.data && <div className="hrms-surface hrms-directory">
      <div className="hrms-directory-heading"><span className="hrms-work-icon"><Users size={22} strokeWidth={1.25} /></span><div><h2>Employee directory</h2><p>{visible.length} of {employees.data.length} employees</p></div></div><div className="hrms-table-scroll">
      <table className="hrms-people-table"><thead className="bg-slate-50 text-slate-600"><tr>
        {['Name', 'Code', 'Department', 'Designation', 'Access role', 'Employment', 'Company joining date', 'Skills'].map((heading) => <th key={heading} className="p-3">{heading}</th>)}
      </tr></thead><tbody>{visible.map((employee) => <tr key={employee.entity_id} className="border-t border-slate-100">
        <td className="p-3"><strong>{employee.full_name}</strong><span className="hrms-employee-email">{employee.work_email}</span></td><td className="p-3">{employee.employee_code}</td><td className="p-3">{employee.department}</td>
        <td className="p-3">{employee.designation}</td>
        <td className="p-3">{labelForRole(employee.role)}</td><td className="p-3"><span className="hrms-status" data-state={isInactive(employee) ? 'offboarded' : exitStage(employee) === 'none' ? employee.employment_status : 'pending'}>{statusLabel(employee)}</span></td>
        <td className="p-3">{joiningDate(employee.date_joined)}</td>
        <td className="p-3">{skillsLabel(employee.custom?.skills)}</td>
      </tr>)}{visible.length === 0 && <tr><td colSpan={8} className="hrms-empty-message">No employees match your filters.</td></tr>}</tbody></table></div>
    </div>}
  </main>;
}
