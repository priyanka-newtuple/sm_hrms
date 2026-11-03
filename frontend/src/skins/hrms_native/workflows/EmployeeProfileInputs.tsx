import { ConfiguredInputs, type Field, type FieldAdapter } from '../forms/ConfiguredForm';

const sameAddress='permanent_same_as_current';
const parts=['address_line_1','address_line_2','city','state','postal_code','country'];
export function copyProfileAddress(fields:Field[],values:Record<string,unknown>){
 const configured=new Map(fields.map(f=>[f.field,f]));
 if(!configured.has(sameAddress)||values[sameAddress]!==true)return values;
 const next={...values};
 for(const part of parts){const source=`current_${part}`,target=`permanent_${part}`;
  if(configured.has(source)&&configured.has(target)&&!configured.get(target)?.read_only)next[target]=values[source]??'';
 }
 return next;
}
export function EmployeeProfileInputs({fields,values,onChange,adapters,entityId}:{fields:Field[];values:Record<string,unknown>;onChange:(v:Record<string,unknown>)=>void;adapters:Record<string,FieldAdapter>;entityId:string}){
 const enabled=fields.some(f=>f.field===sameAddress&&!f.read_only)&&values[sameAddress]===true;
 const canCopy=parts.every(part=>fields.some(f=>f.field===`current_${part}`)&&fields.some(f=>f.field===`permanent_${part}`&&!f.read_only));
 const displayed=enabled&&canCopy?fields.filter(f=>!parts.some(part=>f.field===`permanent_${part}`)):fields;
 return <><ConfiguredInputs fields={displayed} values={values} onChange={v=>onChange(copyProfileAddress(fields,v))} adapters={adapters} entityId={entityId}/>
 {enabled&&canCopy&&<p role="status" className="text-sm sm:col-span-2">Your current address will also be saved as your permanent address. Uncheck the box to enter a different address.</p>}</>;
}
