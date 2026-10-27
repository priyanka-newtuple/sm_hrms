import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import AssetsPage, {AssetForm} from './AssetsPage';
const state=vi.hoisted(()=>({fail:false,duplicate:false,posts:[] as Record<string,unknown>[]}));
vi.mock('../capabilities',()=>({useHrmsCapabilities:()=>({data:{capabilities:['asset:manage']}})}));
vi.mock('../components/PageHero',()=>({PageHero:({actions}:{actions:React.ReactNode})=><div>{actions}</div>}));
vi.mock('@/core/services/api/client',()=>({getApiErrorMessage:(e:Error)=>e.message,request:async(path:string,options?:{body:string})=>{
 if(path.includes('pending-'))return {items:[]};
 if(options?.body){state.posts.push(JSON.parse(options.body));if(state.duplicate)throw Object.assign(new Error('An asset with this asset tag already exists'),{status:409});if(state.fail)throw new Error('Connection interrupted');return path.endsWith('batch-create')?{complete:true,total:2,items:[{item:1,status:'created',identifier:'AST-1'},{item:2,status:'created',identifier:'AST-2'}]}:{entity_id:'asset'};}
 if(path.includes('/forms/'))return {fields:[{field:'issued_employee_id',type:'string'},{field:'issued_date',type:'date'},{field:'issue_note',type:'text'},{field:'asset_tag',type:'string',required:true},{field:'asset_name',type:'string',required:true},{field:'asset_category',type:'enum',enum_values:['Configured laptop'],required:true}]};
 return {items:[{id:'asset',data:{asset_name:'Laptop',asset_tag:'NT-1'},state:'available',employee_name:'',actions:['issue']}],can_manage:true,employees:[{id:'employee',label:'Employee One'}]};
}}));
afterEach(()=>{cleanup();state.fail=false;state.duplicate=false;state.posts=[];});
function legacy(action:string){render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})}><AssetForm action={action} asset={action==='issue'?{id:'asset',data:{},employee_name:'',state:'available',actions:['issue']}:undefined} employees={[{id:'employee',label:'Employee One'}]} done={()=>{}}/></QueryClientProvider>);}
function show(){render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})}><AssetsPage/></QueryClientProvider>);}
it('renders native text and configured select fields',async()=>{
 show();fireEvent.click(await screen.findByRole('button',{name:'Add assets'}));
 expect((await screen.findByLabelText('Asset name')).tagName).toBe('INPUT');
 expect((await screen.findByLabelText('Asset category')).tagName).toBe('SELECT');
 expect(screen.getByRole('option',{name:'Configured laptop'})).toBeTruthy();
});
it('retries issuance with the same key and employee',async()=>{
 legacy('issue');
 fireEvent.change(await screen.findByLabelText('Employee'),{target:{value:'employee'}});
 state.fail=true;fireEvent.submit(screen.getByRole('button',{name:'Issue asset'}).closest('form')!);
 await screen.findByRole('alert');state.fail=false;
 fireEvent.click(screen.getByRole('button',{name:'Retry'}));
 await waitFor(()=>expect(state.posts).toHaveLength(2));
 expect(state.posts[0]).toEqual(state.posts[1]);
 expect(state.posts[0]).toMatchObject({action:'issue',data:{issued_employee_id:'employee'}});
});

it('lets a duplicate tag be corrected and submitted with a fresh operation key',async()=>{
 legacy('create');
 const tag=await screen.findByLabelText('Asset tag');
 fireEvent.change(tag,{target:{value:'Laptop'}});
 state.duplicate=true;
 fireEvent.submit(screen.getByRole('button',{name:'Save asset'}).closest('form')!);
 await screen.findByRole('alert');
 expect((tag.closest('fieldset') as HTMLFieldSetElement).disabled).toBe(false);
 fireEvent.change(tag,{target:{value:'NT-LAP-002'}});
 state.duplicate=false;
 fireEvent.submit(screen.getByRole('button',{name:'Save asset'}).closest('form')!);
 await waitFor(()=>expect(state.posts).toHaveLength(2));
 expect(state.posts[1]).toMatchObject({action:'create',data:{asset_tag:'NT-LAP-002'}});
 expect(state.posts[1].idempotency_key).not.toBe(state.posts[0].idempotency_key);
});

it('submits separate units and reuses the request after a network failure',async()=>{
 show();fireEvent.click(await screen.findByRole('button',{name:'Add assets'}));
 fireEvent.change(await screen.findByLabelText('Quantity'),{target:{value:'2'}});
 fireEvent.change(screen.getByLabelText('Asset name'),{target:{value:'Monitor'}});
 fireEvent.change(screen.getByLabelText('Asset category'),{target:{value:'Configured laptop'}});
 fireEvent.submit(screen.getByRole('button',{name:'Review assets'}).closest('form')!);
 state.fail=true;
 fireEvent.submit(screen.getByRole('button',{name:'Create 2 assets'}).closest('form')!);
 await screen.findByRole('alert');state.fail=false;
 fireEvent.click(screen.getByRole('button',{name:'Retry unfinished items'}));
 await waitFor(()=>expect(state.posts).toHaveLength(2));
 expect(state.posts[0]).toEqual(state.posts[1]);
 expect(state.posts[0].units).toHaveLength(2);
 expect(state.posts[0].data).toEqual({asset_name:'Monitor',asset_category:'Configured laptop'});
 await screen.findByText('2 of 2 assets created');
});
