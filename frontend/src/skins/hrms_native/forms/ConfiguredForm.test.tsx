import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {useState} from 'react';
import {ConfiguredForm,ConfiguredInputs,ConfiguredField,NativeFormFields,formValues,type Field} from './ConfiguredForm';
const config=vi.hoisted(()=>({fields:[] as Field[]}));
vi.mock('@/core/hooks/useDocumentTypes',()=>({useDocumentTypes:()=>({documentTypes:[],loading:false,error:null,getDocumentType:()=>undefined,getAllowedExtensions:()=>[],getMaxSizeBytes:()=>10485760})}));
vi.mock('@/core/services/api/client',()=>({request:async()=>({fields:config.fields}),getApiErrorMessage:String}));
afterEach(cleanup);
function Editor({kind}:{kind:string}) {const [values,setValues]=useState<Record<string,unknown>>({retired:'Old value'});return <ConfiguredForm entityType={kind}><ConfiguredInputs values={values} onChange={setValues}/></ConfiguredForm>;}
it.each(['Employee','Customer','Project','Allocation','LeaveRequest','PerformanceCycle','PerformanceGoal','ProjectFeedback','WorkFromHomeRequest','WorkFromHomePolicy','Asset','Policy','LearningEvent','HolidayCalendar','JobDescription','JobOpening'])('%s follows native additions, removal, order, labels and read-only metadata',async kind=>{
 config.fields=[{field:'retired',type:'string',description:'Old label'}];
 const client=new QueryClient({defaultOptions:{queries:{retry:false}}});
 render(<QueryClientProvider client={client}><Editor kind={`HRMS.${kind}`}/></QueryClientProvider>);
 expect((await screen.findByLabelText('Old label') as HTMLInputElement).value).toBe('Old value');
 config.fields=[{field:'choice',type:'enum',description:'Team',required:true,enum_values:['new'],enum_labels:{new:'New team'}},{field:'memo',type:'text',description:'Details',read_only:true}];
 window.dispatchEvent(new Event('form-schemas-changed'));
 await waitFor(()=>expect(screen.queryByLabelText('Old label')).toBeNull());
 expect(screen.getByRole('option',{name:'New team'})).toBeTruthy();
 expect((screen.getByLabelText('Team') as HTMLSelectElement).required).toBe(true);
 expect((screen.getByLabelText('Details') as HTMLTextAreaElement).disabled).toBe(true);
 expect(screen.getByLabelText('Details').tagName).toBe('TEXTAREA');
 fireEvent.change(screen.getByLabelText('Team'),{target:{value:'new'}});
 expect(formValues(config.fields,{retired:'Old value',choice:'new',memo:'injected'})).toEqual({choice:'new'});
 client.clear();
});
it('maps an authorized relationship without making its generated label writable',()=>{
 const fields:Field[]=[{field:'reports_to_employee_code',type:'string'},{field:'created_by',type:'string'}];
 expect(formValues(fields,{reports_to_entity_id:'manager',created_by:'attacker'},['created_by'],{reports_to_employee_code:{key:'reports_to_entity_id'}})).toEqual({reports_to_entity_id:'manager'});
});

it('validates configured phone inputs and clears the error after correction',()=>{
 function PhoneEditor(){const [values,setValues]=useState<Record<string,unknown>>({contact:''});return <ConfiguredInputs fields={[{field:'contact',type:'phone',description:'Contact'}]} values={values} onChange={setValues}/>;}
 render(<PhoneEditor/>);
 const input=screen.getByLabelText('Contact') as HTMLInputElement;
 expect(input.type).toBe('tel');
 expect(input.checkValidity()).toBe(true);
 fireEvent.change(input,{target:{value:'kjkjkjk'}});
 expect(input.checkValidity()).toBe(false);
 expect(input.validationMessage).toContain('valid phone number');
 fireEvent.input(input,{target:{value:'+91 98765 43210'}});
 expect(input.checkValidity()).toBe(true);
 fireEvent.input(input,{target:{value:'1234567890123456'}});
 expect(input.checkValidity()).toBe(false);
});

it('shows a reporting manager name while saving the employee code',()=>{
 const change=vi.fn();
 render(<ConfiguredInputs fields={[{field:'reports_to_employee_code',type:'string',description:'Reports to employee code'}]} values={{reports_to_employee_code:'EMP-0003'}} onChange={change} adapters={{reports_to_employee_code:{options:[{id:'EMP-0003',name:'Priyanka Nambiar · EMP-0003'},{id:'EMP-0002',name:'Shikha Hossein · EMP-0002'}]}}}/>);
 const select=screen.getByLabelText('Reports to employee code') as HTMLSelectElement;
 expect(select.selectedOptions[0].textContent).toBe('Priyanka Nambiar · EMP-0003');
 fireEvent.change(select,{target:{value:'EMP-0002'}});
 expect(change).toHaveBeenCalledWith({reports_to_employee_code:'EMP-0002'});
});

it('renders multi-select values separately and submits an array',()=>{
 render(<ConfiguredInputs fields={[{field:'skills',type:'multi_select',description:'Skills',enum_values:['Python','SQL']}]} values={{skills:['Python','SQL']}} onChange={()=>{}}/>);
 expect(screen.getByRole('group',{name:'Skills'})).toBeTruthy();
 expect(screen.getByText('Python')).toBeTruthy();
 expect(screen.getByText('SQL')).toBeTruthy();
 expect(formValues([{field:'skills',type:'multi_select'}],{skills:['Python','SQL']})).toEqual({skills:['Python','SQL']});
});


it.each(['string','text','phone','email','date','datetime','enum','multi_select','boolean','document'])('marks required %s fields once using native metadata', type=>{
 const {container,rerender}=render(<ConfiguredInputs fields={[{field:'answer',description:'Answer',type,required:true}]} values={{}} onChange={()=>{}}/>);
 expect(container.querySelectorAll('[title="Required"]').length).toBe(1);
 rerender(<ConfiguredInputs fields={[{field:'answer',description:'Answer',type,required:false}]} values={{}} onChange={()=>{}}/>);
 expect(container.querySelectorAll('[title="Required"]').length).toBe(0);
 rerender(<ConfiguredInputs fields={[{field:'answer',description:'Answer',type,required:true,read_only:true}]} values={{}} onChange={()=>{}}/>);
 expect(container.querySelectorAll('[title="Required"]').length).toBe(0);
});
it('shows draft requirements without blocking incomplete draft saves',()=>{
 const {container}=render(<form><ConfiguredInputs validateRequired={false} fields={[{field:'email',type:'email',required:true},{field:'confirm',type:'boolean',required:true}]} values={{}} onChange={()=>{}}/></form>);
 expect(container.querySelectorAll('[title="Required"]').length).toBe(2);
 expect(container.querySelector('form')!.checkValidity()).toBe(true);
 expect(screen.getByLabelText('Email').getAttribute('aria-required')).toBe('true');
});
it('prefers native requirements to custom input defaults',()=>{
 const {container}=render(<NativeFormFields fields={[{field:'answer',required:false}]}><ConfiguredField field="answer" label="Answer"><input required/></ConfiguredField><ConfiguredField operational field="quantity" label="Quantity"><input required/></ConfiguredField></NativeFormFields>);
 expect(container.querySelectorAll('[title="Required"]').length).toBe(1);
 expect((screen.getByLabelText('Answer') as HTMLInputElement).required).toBe(false);
 expect((screen.getByLabelText('Quantity') as HTMLInputElement).required).toBe(true);
});
