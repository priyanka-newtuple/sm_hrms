import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {useState} from 'react';
import {ConfiguredForm,ConfiguredInputs,formValues,type Field} from './ConfiguredForm';
const config=vi.hoisted(()=>({fields:[] as Field[]}));
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
