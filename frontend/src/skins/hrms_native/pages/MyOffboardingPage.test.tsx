import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter,Route,Routes} from 'react-router-dom';
import MyOffboardingPage from './MyOffboardingPage';

const state=vi.hoisted(()=>({posts:[] as Record<string,unknown>[],editable:true,participant:false,contact:false}));
vi.mock('@/core/services/api/client',()=>({getApiErrorMessage:(e:Error)=>e.message,request:async(_path:string,options?:{body:string})=>{
  if(options?.body){state.posts.push(JSON.parse(options.body));return {};}
  if(state.participant)return {entity_id:'exit',viewer:'participant',state:'Pending Clearance',values:{exit_employee_name:'Example Employee'},values_hash:'hash',editable:false,fields:[],actions:[]};
  const fields=state.contact?[{field:'employee_notification_email',description:'Personal email',type:'email',enum_values:[],required:true},{field:'notification_email_confirmed',description:'Confirm contact email',type:'enum',enum_values:['Yes'],required:true},{field:'exit_acknowledgment',description:'I confirm the information is accurate',type:'boolean',enum_values:[],required:true}]:[{field:'exit_assets_returned',description:'All assets returned?',type:'enum',enum_values:['Yes','No'],required:true},{field:'exit_assets_returned_remarks',description:'Pending actions',type:'text'}];
  return {entity_id:'exit',state:state.editable?'In Progress':'Submitted',values:{},values_hash:'hash',editable:state.editable,fields,sections:[{title:'Access & Asset Clearance',fields}],actions:state.editable?[{trigger:'submit_checklist',label:'Submit checklist'}]:[]};
}}));
afterEach(()=>{cleanup();state.posts=[];state.editable=true;state.participant=false;state.contact=false;});
function show(){render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter initialEntries={['/exit/one']}><Routes><Route path="/exit/:id" element={<MyOffboardingPage/>}/></Routes></MemoryRouter></QueryClientProvider>);}

it('shows native section labels and saves an incomplete draft',async()=>{
  show();await screen.findByRole('heading',{name:'Access & Asset Clearance'});
  expect(screen.getByText('0 / 1 answered')).toBeTruthy();
  expect(screen.queryByLabelText('Pending actions')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Save draft'}));
  await waitFor(()=>expect(state.posts).toHaveLength(1));
  expect(state.posts[0]).toMatchObject({values:{},trigger:''});
});

it('No is answered and displays remarks, while unanswered submission shows an inline error',async()=>{
  show();fireEvent.click(await screen.findByRole('button',{name:'Submit checklist'}));
  expect(screen.getByText('Please complete this answer.')).toBeTruthy();
  expect(state.posts).toHaveLength(0);
  fireEvent.click(screen.getByRole('radio',{name:'No'}));
  expect(screen.getByText('1 / 1 answered')).toBeTruthy();
  expect(screen.getByLabelText('Pending actions')).toBeTruthy();
});

it('submitted responses cannot be edited or resubmitted',async()=>{
  state.editable=false;show();
  const answer=await screen.findByRole('radio',{name:'Yes'});
  expect(answer.closest('form')!.querySelector('fieldset')!.disabled).toBe(true);
  expect(screen.queryByRole('button',{name:'Save draft'})).toBeNull();
  expect(screen.queryByRole('button',{name:'Submit checklist'})).toBeNull();
});


it('shows participant progress without an employee form or actions',async()=>{
  state.participant=true;show();
  expect(await screen.findByRole('heading',{name:'Offboarding · Example Employee'})).toBeTruthy();
  expect(screen.getByText('Pending Clearance')).toBeTruthy();
  expect(screen.queryByRole('button',{name:'Save draft'})).toBeNull();
  expect(screen.queryByRole('button',{name:'Submit checklist'})).toBeNull();
  expect(screen.queryByRole('radio')).toBeNull();
});

it('renders email and declaration despite empty choices and reconfirms changed email',async()=>{
 state.contact=true;show();
 const email=await screen.findByRole('textbox',{name:'Personal email *'});
 fireEvent.change(email,{target:{value:'personal@example.com'}});
 fireEvent.click(screen.getByRole('radio',{name:'Yes'}));
 fireEvent.click(screen.getByRole('checkbox',{name:'I confirm the information is accurate *'}));
 fireEvent.change(email,{target:{value:'updated@example.com'}});
 expect((screen.getByRole('radio',{name:'Yes'}) as HTMLInputElement).checked).toBe(false);
 expect(screen.getByText('Confirm that updated@example.com is your personal email for correspondence after exit.')).toBeTruthy();
 fireEvent.click(screen.getByRole('radio',{name:'Yes'}));
 fireEvent.click(screen.getByRole('button',{name:'Save draft'}));
 await waitFor(()=>expect(state.posts).toHaveLength(1));
 expect(state.posts[0]).toMatchObject({values:{employee_notification_email:'updated@example.com',notification_email_confirmed:'Yes',exit_acknowledgment:true}});
});
