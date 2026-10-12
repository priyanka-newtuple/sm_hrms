import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import AddEmployee from './AddEmployee';
const access = vi.hoisted(() => ({ allowed: true }));
vi.mock('../capabilities', () => ({useHrmsCapabilities: () => ({data:{capabilities:access.allowed ? ['employee:create'] : []}})}));
vi.mock('../../../core/services/api/client', () => ({getApiErrorMessage:String, request:vi.fn(async (path:string) => path.endsWith('form-options') ? {departments:[],designations:[],roles:['custom_engineer'],role_labels:{custom_engineer:'Senior Engineer'}} : [])}));
vi.mock('../forms/ConfiguredForm', () => ({ConfiguredForm:({children}:{children:React.ReactNode}) => children, ConfiguredField:({children,label}:{children:React.ReactNode;label:string}) => <label>{label}{children}</label>}));
afterEach(() => {cleanup();access.allowed=true;});
function show() {return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter><AddEmployee/></MemoryRouter></QueryClientProvider>);}
it('opens employee creation from onboarding', async () => {
 show();
 fireEvent.click(screen.getByRole('button',{name:'Add employee / Start onboarding'}));
 expect(await screen.findByRole('button',{name:'Create employee & start onboarding'})).toBeTruthy();
 expect(screen.getByLabelText(/Work email/)).toBeTruthy();
});
it('hides employee creation without permission', () => {
 access.allowed=false;show();
 expect(screen.queryByRole('button',{name:'Add employee / Start onboarding'})).toBeNull();
});


it('uses the native role display name and requires a selection', async () => {
 show();
 fireEvent.click(screen.getByRole('button',{name:'Add employee / Start onboarding'}));
 expect(await screen.findByRole('option',{name:'Senior Engineer'})).toBeTruthy();
 expect((screen.getByLabelText('Access role') as HTMLSelectElement).value).toBe('');
 expect(screen.getByText(/All new accounts require Super Admin approval/)).toBeTruthy();
});
