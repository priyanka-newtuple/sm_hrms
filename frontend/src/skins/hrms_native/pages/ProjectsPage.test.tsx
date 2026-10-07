import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ProjectAction } from './ProjectsPage';

const state = vi.hoisted(() => ({allowed:true, readonly:false, fail:false, posts:[] as Record<string, unknown>[]}));
vi.mock('../capabilities', () => ({useHrmsCapabilities:()=>({data:{capabilities:state.allowed ? ['customer:create'] : []}})}));
vi.mock('@/core/services/api/client', () => ({
  getApiErrorMessage:(error:Error)=>error.message,
  request:vi.fn(async (path:string, options?:{body:string})=>{
    if (path.includes('/forms/')) return {fields:state.readonly && path.endsWith('HRMS.Project') ? [{field:'customer_name', read_only:true}] : []};
    if (path.endsWith('/options')) return {customers:[],pms:[],dms:[],approvers:[],employees:[],project_roles:[]};
    if (options?.body) {
      state.posts.push(JSON.parse(options.body));
      if (state.fail) throw new Error('Network unavailable');
      return {entity_id:'customer-new'};
    }
    return [];
  }),
}));
function show() {
  const client = new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});
  return render(<QueryClientProvider client={client}><ProjectAction action="create_project" done={vi.fn()} /></QueryClientProvider>);
}
async function startCustomer() {
  fireEvent.change(await screen.findByLabelText('Name'), {target:{value:'Project draft'}});
  fireEvent.click(await screen.findByRole('button',{name:'Create customer'}));
  await screen.findByRole('heading',{name:'Create customer'});
  fireEvent.change(await screen.findByLabelText('Name'), {target:{value:'New customer'}});
}
beforeEach(()=>{state.allowed=true;state.readonly=false;state.fail=false;state.posts=[];});
afterEach(cleanup);

describe('Customer creation within a project draft',()=>{
  it('creates through the existing command, selects the result and preserves the project draft',async()=>{
    show(); await startCustomer();
    expect(document.querySelector('form form')).toBeNull();
    fireEvent.submit(screen.getByRole('button',{name:'Create customer'}).closest('form')!);
    await screen.findByRole('heading',{name:'Create project'});
    expect((screen.getByLabelText('Name') as HTMLInputElement).value).toBe('Project draft');
    expect((screen.getByLabelText('Customer') as HTMLSelectElement).value).toBe('customer-new');
    expect(screen.getByRole('option',{name:'New customer'})).toBeTruthy();
    expect(state.posts[0]).toMatchObject({action:'create_customer',data:{name:'New customer'}});
  });
  it('returns to the unchanged project when customer creation is cancelled',async()=>{
    show(); await startCustomer();
    fireEvent.click(screen.getByRole('button',{name:'Cancel'}));
    expect((await screen.findByLabelText('Name') as HTMLInputElement).value).toBe('Project draft');
    expect((screen.getByLabelText('Customer') as HTMLSelectElement).value).toBe('');
    expect(state.posts).toHaveLength(0);
  });
  it('keeps the customer form on failure and reuses the operation key on retry',async()=>{
    show(); await startCustomer(); state.fail=true;
    fireEvent.submit(screen.getByRole('button',{name:'Create customer'}).closest('form')!);
    await screen.findByRole('alert');
    expect(screen.getByRole('heading',{name:'Create customer'})).toBeTruthy();
    state.fail=false;
    fireEvent.submit(screen.getByRole('button',{name:'Retry action'}).closest('form')!);
    await waitFor(()=>expect(state.posts).toHaveLength(2));
    expect(state.posts[1].idempotency_key).toBe(state.posts[0].idempotency_key);
    await screen.findByRole('heading',{name:'Create project'});
  });
  it.each(['permission','readonly'])('hides creation for %s restrictions',async restriction=>{
    state.allowed=restriction!=='permission'; state.readonly=restriction==='readonly';
    show(); await screen.findByLabelText('Customer');
    expect(screen.queryByRole('button',{name:'Create customer'})).toBeNull();
  });
});
