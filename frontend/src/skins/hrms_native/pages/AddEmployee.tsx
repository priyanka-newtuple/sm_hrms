import { createRequestId } from '../requestId';
import { ConfiguredForm, ConfiguredInputs, useFormSchema, commandValues, employeeSystemFields, employeeAdapters } from '../forms/ConfiguredForm';
import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
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
export interface CreatedEmployee {
  employee: Employee;
  account_status: string;
}

export function EmployeeCreatedNotice({created}: {created: CreatedEmployee | null}) {
  return created ? <div role="status" className="hrms-notice">
    <strong>{created.employee.full_name} ({created.employee.employee_code}) was added.</strong>{' '}
    {created.account_status === 'not_created' ? 'Registration saved. Continue the configured workflow from My Tasks.' : `Account status: ${created.account_status}. Review the account in Settings → Users.`}
  </div> : null;
}

export default function AddEmployee({buttonClassName = '', onCreated}: {buttonClassName?: string; onCreated?: (created: CreatedEmployee | null) => void} = {}) {
  const { data: capabilities } = useHrmsCapabilities();
  const canCreate = capabilities?.capabilities.includes('employee:create') ?? false;
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [created, setCreated] = useState<CreatedEmployee | null>(null);
  const [error, setError] = useState('');
  const schema=useFormSchema('HRMS.Employee',canCreate&&showForm,'registration');
  const [key, setKey] = useState(() => createRequestId());
  const [form, setForm] = useState<Record<string,unknown>>({
    first_name: '', last_name: '', work_email: '', department: '', designation: '',
    role: '', reports_to_entity_id: '', date_joined: new Date().toISOString().slice(0, 10),
    employment_type: '', notice_period_days: '', phone: '', work_location: '',
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
        ...commandValues(schema.data?.fields??[],form,employeeSystemFields,employeeAdapters),
        idempotency_key: key,
      }),
    }),
    onSuccess: (result) => {
      setError(''); setShowForm(false); setKey(createRequestId());
      setCreated(result);
      onCreated?.(result);
      void queryClient.invalidateQueries({ queryKey: ['hrms'] });
    },
    onError: (cause) => setError(getApiErrorMessage(cause)),
  });
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); create.mutate(); }

  if (!canCreate) return null;
  return <>
    <button type="button" className={`hrms-primary-button ${buttonClassName}`} onClick={() => { setCreated(null); onCreated?.(null); setShowForm(true); }}><Plus size={16} /> Add employee</button>
    {!onCreated && <EmployeeCreatedNotice created={created}/>}
    <Sheet open={showForm} onOpenChange={setShowForm}>
      <SheetContent className="hrms-brand hrms-employee-form overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-2xl">
        <SheetHeader><p className="hrms-eyebrow">GROW THE TEAM</p><SheetTitle>Add Employee</SheetTitle><p className="hrms-form-intro">Enter the employee details. New accounts require approval before sign-in.</p></SheetHeader>
        {options.isError && <div role="alert" className="hrms-notice hrms-notice--error">{getApiErrorMessage(options.error)}<button className="hrms-outline-button" onClick={() => void options.refetch()}>Try again</button></div>}
        {employees.isError && <div role="alert" className="hrms-notice hrms-notice--error">Unable to load reporting managers. <button className="hrms-outline-button" onClick={() => void employees.refetch()}>Try again</button></div>}
        <ConfiguredForm entityType="HRMS.Employee" purpose="registration" optionsLoading={options.isLoading||employees.isLoading} loadingMessage="Loading employee form…"><form onSubmit={submit} className="hrms-people-form">
          <div className="grid gap-3 sm:grid-cols-2"><ConfiguredInputs values={form} onChange={values=>{setForm(values);setKey(createRequestId());}} exclude={employeeSystemFields} adapters={{
            ...employeeAdapters,
            hrms_role:{...employeeAdapters.hrms_role,options:(options.data?.roles??[]).map(id=>({id,name:options.data?.role_labels[id]??id}))},
            reports_to_employee_code:{...employeeAdapters.reports_to_employee_code,options:(employees.data??[]).filter(e=>e.employment_status==='active').map(e=>({id:e.entity_id,name:e.full_name}))}
          }}/></div>
          {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
          <div className="hrms-form-actions"><button type="button" onClick={() => setShowForm(false)} className="hrms-outline-button">Cancel</button><button type="submit" disabled={create.isPending || !options.data || !schema.data || employees.isError} className="hrms-primary-button">{create.isPending ? 'Creating…' : 'Create employee'}</button></div>
        </form></ConfiguredForm>
      </SheetContent>
    </Sheet>
  </>;
}
