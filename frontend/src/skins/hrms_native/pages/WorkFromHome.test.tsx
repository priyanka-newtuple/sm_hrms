import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { WorkFromHome, type WfhBoard } from './WorkFromHome';
import { request } from '@/core/services/api/client';

vi.mock('../capabilities', () => ({ useHrmsCapabilities: () => ({ data: { capabilities: ['wfh:view','wfh:request','wfh:approve'] } }) }));
vi.mock('@/core/services/api/client', () => ({ request: vi.fn(), getApiErrorMessage: (e: Error) => e.message }));
vi.mock('../forms/ConfiguredForm', () => ({ ConfiguredForm: ({ children }: {children: React.ReactNode}) => children, ConfiguredField: ({ label, children }: {label: string; children: React.ReactNode}) => <label>{label}{children}</label> }));
vi.mock('../components/WorkPanel', () => ({ WorkPanel: () => null }));
const api = vi.mocked(request);
let board: WfhBoard;
let client: QueryClient;
beforeEach(() => {
  board = { policy: {year: new Date().getFullYear(), annual_days: 24, notice_days: 0, revision: 1}, requests: [], calendar: [], can_configure: true, can_approve: true, can_request: true, balance: {used: 0, upcoming: 0, pending: 0, remaining: 24} };
  api.mockImplementation(async () => board);
  client = new QueryClient({defaultOptions: {queries: {retry: false, gcTime: 0}, mutations: {retry: false}}});
});
afterEach(() => { cleanup(); client.clear(); vi.clearAllMocks(); });
function show(cockpit = false) { render(<QueryClientProvider client={client}><MemoryRouter><WorkFromHome cockpit={cockpit} /></MemoryRouter></QueryClientProvider>); }

it('puts policy configuration inside HR Cockpit', async () => {
  show(true);
  fireEvent.click(await screen.findByRole('button', {name: 'Policy'}));
  fireEvent.change(screen.getByLabelText('Annual allowance (days)'), {target: {value: '30'}});
  fireEvent.click(screen.getByRole('button', {name: 'Save policy'}));
  await waitFor(() => expect(api).toHaveBeenCalledWith('/hrms/wfh/policy', expect.objectContaining({method: 'POST'})));
  const call = api.mock.calls.find(c => c[0] === '/hrms/wfh/policy');
  expect(JSON.parse(call![1]!.body as string)).toMatchObject({annual_days: 30, revision: 1});
});

it('shows calendar bookings and submits selected weekdays for HR approval', async () => {
  show();
  const next = await screen.findByRole('button', {name: 'Next month'});
  fireEvent.click(next);
  const day = (await screen.findAllByRole('button', {name: /^Request WFH/})).find(b => !(b as HTMLButtonElement).disabled)!;
  fireEvent.click(day);
  fireEvent.click(screen.getByRole('button', {name: 'Submit to HR'}));
  await waitFor(() => expect(api).toHaveBeenCalledWith('/hrms/wfh/requests', expect.objectContaining({method: 'POST'})));
  const call = api.mock.calls.find(c => c[0] === '/hrms/wfh/requests');
  expect(JSON.parse(call![1]!.body as string).dates).toEqual([day.getAttribute('aria-label')!.replace('Request WFH ', '')]);
});

it('shows failures with retry instead of an empty calendar', async () => {
  api.mockRejectedValue(new Error('WFH service unavailable'));
  show();
  expect(await screen.findByRole('alert')).toBeTruthy();
  expect(screen.getByRole('button', {name: 'Try again'})).toBeTruthy();
  expect(screen.queryByRole('group', {name: 'Work location calendar'})).toBeNull();
});

it('keeps HR policy controls out of the employee calendar', async () => {
  board.can_configure = false;
  board.can_approve = false;
  show();
  await screen.findByRole('group', {name: 'Work location calendar'});
  expect(screen.queryByRole('button', {name: 'Policy'})).toBeNull();
});
