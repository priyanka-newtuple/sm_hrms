import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {useState} from 'react';
import {EmployeeProfileInputs,copyProfileAddress} from './EmployeeProfileInputs';
import type {Field} from '../forms/ConfiguredForm';
vi.mock('@/core/services/api/client',()=>({request:vi.fn(),getApiErrorMessage:String}));
afterEach(cleanup);
const parts=['address_line_1','address_line_2','city','state','postal_code','country'];
const fields:Field[]=[{field:'permanent_same_as_current',type:'boolean',description:'Same as current'},...['current_','permanent_'].flatMap(prefix=>parts.map(part=>({field:prefix+part,type:'string',description:prefix+part})))];
it('copies and hides the permanent address, then restores editing',()=>{
 function Editor(){const [values,setValues]=useState<Record<string,unknown>>({current_city:'Pune'});return <EmployeeProfileInputs fields={fields} values={values} onChange={setValues} adapters={{}} entityId="employee"/>;}
 render(<Editor/>);
 fireEvent.click(screen.getByLabelText('Same as current'));
 expect(screen.queryByLabelText('permanent_city')).toBeNull();
 fireEvent.change(screen.getByLabelText('current_city'),{target:{value:'Mumbai'}});
 fireEvent.click(screen.getByLabelText('Same as current'));
 expect((screen.getByLabelText('permanent_city') as HTMLInputElement).value).toBe('Mumbai');
});
it('preserves read-only fields',()=>{
 const result=copyProfileAddress(fields.map(f=>f.field==='permanent_city'?{...f,read_only:true}:f),{permanent_same_as_current:true,current_city:'Pune',permanent_city:'Delhi'});
 expect(result.permanent_city).toBe('Delhi');
});
