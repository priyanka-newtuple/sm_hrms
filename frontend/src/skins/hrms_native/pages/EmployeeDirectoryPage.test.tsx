import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import EmployeeDirectoryPage from './EmployeeDirectoryPage';
import { request } from '../../../core/services/api/client';

vi.mock('../capabilities', () => ({ useHrmsCapabilities: () => ({ data: { capabilities: ['employee:create', 'employee:read'] } }) }));
vi.mock('../forms/ConfiguredForm', () => ({ ConfiguredForm: () => null, ConfiguredField: () => null }));
vi.mock('../../../core/services/api/client', () => ({ request: vi.fn(async () => []), getApiErrorMessage: String }));

const getRandomValues = globalThis.crypto.getRandomValues.bind(globalThis.crypto);
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('renders the employee directory on HTTP when randomUUID is unavailable', async () => {
  vi.stubGlobal('crypto', { getRandomValues });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><MemoryRouter><EmployeeDirectoryPage /></MemoryRouter></QueryClientProvider>);
  expect(await screen.findByRole('heading', { name: 'Org Directory' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Add Employee' })).toBeNull();
  client.clear();
});

it('shows separate account and onboarding status and requests setup from the directory', async () => {
  vi.mocked(request).mockImplementation(async (path) => path.endsWith('/setup-access')
    ? { message: 'Account active. Password setup email requested.' }
    : [{ entity_id: 'employee-1', employee_code: 'EMP-1', full_name: 'New Employee', work_email: 'new@newtuple.com',
      department: 'Engineering', designation: 'Engineer', role: 'hrms_employee', employment_status: 'active',
      account_status: 'pending', onboarding_state: 'in_progress', can_setup_access: true }]);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><MemoryRouter><EmployeeDirectoryPage /></MemoryRouter></QueryClientProvider>);
  expect(await screen.findByText('pending')).toBeTruthy();
  expect(screen.getByText('in progress')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Activate & send setup email' }));
  expect(await screen.findByText('Account active. Password setup email requested.')).toBeTruthy();
  expect(request).toHaveBeenCalledWith('/hrms/employees/employee-1/setup-access', expect.objectContaining({ method: 'POST' }));
  client.clear();
});
