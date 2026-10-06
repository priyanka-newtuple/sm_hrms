import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import EmployeeDirectoryPage from './EmployeeDirectoryPage';

vi.mock('../capabilities', () => ({ useHrmsCapabilities: () => ({ data: { capabilities: ['employee:create', 'employee:read'] } }) }));
vi.mock('../forms/ConfiguredForm', () => ({ ConfiguredForm: () => null, ConfiguredField: () => null }));
vi.mock('../../../core/services/api/client', () => ({ request: vi.fn(async () => []), getApiErrorMessage: String }));

const getRandomValues = globalThis.crypto.getRandomValues.bind(globalThis.crypto);
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('renders the employee directory on HTTP when randomUUID is unavailable', async () => {
  vi.stubGlobal('crypto', { getRandomValues });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><MemoryRouter><EmployeeDirectoryPage /></MemoryRouter></QueryClientProvider>);
  expect(await screen.findByRole('heading', { name: 'Employees' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Add Employee' })).toBeTruthy();
  client.clear();
});
