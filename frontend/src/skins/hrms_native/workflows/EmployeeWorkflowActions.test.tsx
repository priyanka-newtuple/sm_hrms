import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { EmployeeWorkflowActions } from './EmployeeWorkflowActions';
import type { EmployeeWork } from '../workspace/useWaitingActions';

const state = vi.hoisted(() => ({writes: [] as Record<string, unknown>[], fail: false, allowed: true}));
const item = {entity_id:'employee', workflow_id:'workflow', current_state:'Verification', title:'Test employee',
  actions:[{trigger:'approve', label:'Approve details and send to IT', to_state:'IT'}]} as EmployeeWork;
vi.mock('@/core/services/api/client', () => ({getApiErrorMessage: String, request: async (path:string, options?:{body?:string}) => {
  if (path.endsWith('/actions')) {
    state.writes.push(JSON.parse(options!.body!));
    if (state.fail) throw new Error('Assignment could not be confirmed');
    return {};
  }
  if (path === '/hrms/employee-work') return [{...item, actions:state.allowed?item.actions:[]}];
  if (path.includes('/assignees')) return {items:[{id:'office',name:'Office Admin'}],fixed:false,can_assign:true,current:null};
  if (path.includes('/form')) return {name:'Verification',fields:[],previous_fields:[],values:{},current_state:'Verification'};
  throw new Error(path);
}}));
vi.mock('../components/record/RecordTabs', () => ({RecordTabs:({children,actions}:any)=><><div aria-label="Record actions">{actions}</div>{children}</>}));
vi.mock('@/skins/hrms_native/components/record/Sheet', () => ({
  Sheet:({children}:any)=><>{children}</>, SheetContent:({children}:any)=><div>{children}</div>,
  SheetHeader:({children}:any)=><div>{children}</div>, SheetTitle:({children}:any)=><h1>{children}</h1>,
}));
vi.mock('./OnboardingAssets', () => ({OnboardingAssets:()=>null}));
vi.mock('./EmployeeProfileInputs', () => ({EmployeeProfileInputs:()=>null}));
vi.mock('../forms/ConfiguredForm', () => ({ConfiguredInputs:()=>null,NativeFormFields:({children}:any)=><>{children}</>}));
afterEach(()=>{cleanup();state.writes=[];state.fail=false;state.allowed=true;});
function show() {
  const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});
  render(<QueryClientProvider client={client}><EmployeeWorkflowActions item={item} open/></QueryClientProvider>);
}
it('requires an eligible next assignee before handing verification to IT',async()=>{
  show();
  fireEvent.change(await screen.findByLabelText('Move to'),{target:{value:'approve'}});
  const next=await screen.findByLabelText('Next assignee');
  expect((screen.getByRole('button',{name:'Continue'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(next,{target:{value:'office'}});
  fireEvent.click(screen.getByRole('button',{name:'Continue'}));
  await waitFor(()=>expect(state.writes).toHaveLength(1));
  expect(state.writes[0]).toMatchObject({trigger:'approve',next_assignee_id:'office',workflow_id:'workflow'});
});
it('retries an uncertain handover with the same assignment and idempotency key',async()=>{
  state.fail=true;show();
  fireEvent.change(await screen.findByLabelText('Move to'),{target:{value:'approve'}});
  fireEvent.change(await screen.findByLabelText('Next assignee'),{target:{value:'office'}});
  fireEvent.click(screen.getByRole('button',{name:'Continue'}));
  const retry=await screen.findByRole('button',{name:'Retry handover'});
  expect(retry.closest('[aria-label="Record actions"]')).not.toBeNull();
  expect(screen.getAllByRole('alert')).toHaveLength(1);
  expect((screen.getByRole('button',{name:'Save details'}) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole('button',{name:'Continue'}) as HTMLButtonElement).disabled).toBe(true);
  state.fail=false;fireEvent.click(retry);
  await waitFor(()=>expect(state.writes).toHaveLength(2));
  expect(state.writes[1]).toEqual(state.writes[0]);
});
it('does not offer a transition that native workflow permissions exclude',async()=>{
  state.allowed=false;show();
  await screen.findByLabelText('Move to');
  expect(screen.queryByRole('option',{name:'Approve details and send to IT'})).toBeNull();
});
