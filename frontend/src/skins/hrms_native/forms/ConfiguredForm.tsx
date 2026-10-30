import DocumentFieldInput from '@/core/components/DocumentFieldInput';
import type { FormField } from '@/core/types';
import { Children, cloneElement, createContext, isValidElement, useContext, useEffect, type ReactElement, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { request, getApiErrorMessage } from '@/core/services/api/client';

export type Field = { document_config?: FormField['document_config']; field: string; description?: string; placeholder?: string; required?: boolean; read_only?: boolean; col_span?: number; type?: string; enum_values?: string[]; custom?: boolean; enum_labels?: Record<string,string> };
type Schema = { name: string; fields: Field[]; workflow_versioned?: boolean };
const Context = createContext<{ fields: Field[]; aliases: Record<string,string> }>({fields:[],aliases:{}});

export type FieldAdapter = { key?: string; label?: string; options?: {id:string;name:string}[]; action?: ReactNode; readOnly?: boolean; type?: string };
export function useFormSchema(entityType:string, enabled=true, purpose='record') {
  return useQuery({queryKey:['hrms','form-config',entityType,purpose],queryFn:()=>request<Schema>(`/hrms/forms/${entityType}?purpose=${purpose}`),enabled,staleTime:0,refetchOnMount:'always'});
}
/** Only currently configured editable fields enter a command. Aliases are explicit relationship adapters. */
export function formValues(fields:Field[], values:Record<string,unknown>, exclude:string[]=[], adapters:Record<string,FieldAdapter>={}) {
  return Object.fromEntries(fields.filter(f=>!exclude.includes(f.field)&&!f.read_only&&!adapters[f.field]?.readOnly)
    .map(f=>adapters[f.field]?.key??f.field).filter(k=>values[k]!==undefined).map(k=>[k,values[k]]));
}
/** Legacy command envelopes keep custom attributes separate; both groups use the same native form. */
export function commandValues(fields:Field[], values:Record<string,unknown>, exclude:string[]=[], adapters:Record<string,FieldAdapter>={}) {
  const current=formValues(fields,values,exclude,adapters);
  const customKeys=new Set(fields.filter(f=>f.custom).map(f=>f.field));
  return {...Object.fromEntries(Object.entries(current).filter(([k])=>!customKeys.has(k))),
    custom:Object.fromEntries(Object.entries(current).filter(([k])=>customKeys.has(k)))};
}
export const employeeSystemFields=['employee_code','employment_status','platform_user_id','identifier','hrms_operation_key','last_working_day','exit_reason','exit_note'];
export const employeeAdapters={hrms_role:{key:'role',label:'Access role'},reports_to_employee_code:{key:'reports_to_entity_id',label:'Reporting manager'}};
export function ConfiguredInputs({values,onChange,exclude=[],fields:provided,adapters={},entityId}:{values:Record<string,unknown>;onChange:(values:Record<string,unknown>)=>void;exclude?:string[];fields?:Field[];adapters?:Record<string,FieldAdapter>;entityId?:string}) {
  const context=useContext(Context);
  return <>{(provided??context.fields).filter(f=>!exclude.includes(f.field)).map(f=>{
    const adapter=adapters[f.field]??{}, key=adapter.key??f.field, type=adapter.type??f.type??'string', value=values[key];
    const set=(v:unknown)=>onChange({...values,[key]:v});
    const numeric=['integer','int','number','float','decimal','timer_duration'].includes(type);
    const supported=['string','str','text','email','phone','url','date','datetime','enum','boolean','bool'].includes(type)||numeric;
    const readonly=!!f.read_only||!!adapter.readOnly;
    const common={className:'hrms-field-input',required:!!f.required&&!readonly,disabled:readonly||(!supported&&!adapter.options),placeholder:f.placeholder};
    const title=f.description?.trim()||adapter.label||key.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());
    const choices=adapter.options??(f.enum_values??[]).map(v=>({id:v,name:f.enum_labels?.[v]??v}));
    const display=value==null?'':typeof value==='object'?JSON.stringify(value):String(value);
    const inputDisplay=type==='datetime' ? (/^\d{4}-\d{2}-\d{2}$/.test(display)?`${display}T00:00`:display.replace(' ','T').slice(0,16)) : display;
    return <div key={f.field} className={f.col_span===2?'sm:col-span-2':''}><label className="block space-y-1 text-sm"><span>{title}</span>{type==='document'?<DocumentFieldInput field={{id:f.field,label:title,type:'document',required:!!f.required,system:false,document_config:f.document_config}} value={value} onChange={set} disabled={readonly||!entityId} entityId={entityId}/>:adapter.options||type==='enum'||!!f.enum_values?.length?
      <select {...common} value={display} onChange={e=>set(e.target.value)}><option value="">Select…</option>{choices.map(v=><option key={v.id} value={v.id}>{v.name}</option>)}</select>
      :['boolean','bool'].includes(type)?<input type="checkbox" disabled={common.disabled} checked={value===true} onChange={e=>set(e.target.checked)}/>
      :type==='text'?<textarea {...common} value={display} onChange={e=>set(e.target.value)}/>
      :<input {...common} type={numeric?'number':type==='date'?'date':type==='datetime'?'datetime-local':type==='phone'?'tel':['email','url'].includes(type)?type:'text'} step={['float','decimal'].includes(type)?'any':1} value={inputDisplay} onChange={e=>set(numeric?(e.target.value===''?null:Number(e.target.value)):e.target.value)}/>}</label>{!readonly&&adapter.action}</div>;
  })}</>;
}

export function ConfiguredForm({entityType, aliases = {}, children, purpose='record', optionsLoading=false, loadingMessage='Loading form configuration…'}: {entityType: string; aliases?: Record<string,string>; children: ReactNode; purpose?:string; optionsLoading?:boolean; loadingMessage?:string}) {
  const client = useQueryClient();
  const schema = useFormSchema(entityType,true,purpose);
  useEffect(() => {
    const refresh = () => { void client.invalidateQueries({queryKey:['hrms','form-config']}); };
    window.addEventListener('form-schemas-changed',refresh);
    return () => window.removeEventListener('form-schemas-changed',refresh);
  },[client]);
  if (schema.isLoading || optionsLoading) return <p role="status">{loadingMessage}</p>;
  if (schema.isError) return <p role="alert">{getApiErrorMessage(schema.error)} <button type="button" onClick={()=>void schema.refetch()}>Retry</button></p>;
  return <Context.Provider value={{fields:schema.data?.fields??[],aliases}}>{schema.data?.workflow_versioned&&<p className="text-xs text-slate-500 mb-3">Fields follow the published workflow form. After editing its form in Settings, publish the updated workflow to apply that version.</p>}{children}</Context.Provider>;
}

export function NativeFormFields({fields, children}: {fields: Field[]; children: ReactNode}) {
  return <Context.Provider value={{fields, aliases:{}}}>{children}</Context.Provider>;
}

/** Keep authorized options and command types; overlay tenant presentation metadata. */
export function ConfiguredField({field, label, children, action, operational = false, className = 'block space-y-1 text-sm'}: {field:string; label:string; children:ReactNode; action?:ReactNode; operational?:boolean; className?:string}) {
  const context = useContext(Context);
  const config = context.fields.find(f=>f.field===(context.aliases[field]??field));
  if (!config && !operational) return null;
  const text = config?.description?.trim() || label;
  const content = Children.map(children, child => {
    if (!isValidElement(child) || !['input','textarea','select'].includes(String(child.type))) return child;
    const control = child as ReactElement<Record<string,unknown>>;
    const props = control.props;
    const select = child.type === 'select';
    const readonly = Boolean(config?.read_only);
    const configured: Record<string,unknown> = {
      required: Boolean(config ? config.required && !readonly : props.required),
      placeholder: config?.placeholder ?? props.placeholder,
      readOnly: select ? undefined : Boolean(props.readOnly || readonly),
      disabled: Boolean(props.disabled || (select && readonly)),
    };
    if (select && config?.enum_values && !field.endsWith('_id')) {
      configured.children = [<option key="" value="">Select…</option>, ...config.enum_values.map(value =>
        <option key={value} value={value}>{config.enum_labels?.[value]??value}</option>)];
    }
    return cloneElement(control,configured);
  });
  if (action && !config?.read_only) return <div className={`${className} ${config?.col_span===2?'sm:col-span-2':''}`}><label className="block space-y-1"><span>{text}</span>{content}</label>{action}</div>;
  return <label className={`${className} ${config?.col_span===2?'sm:col-span-2':''}`}><span>{text}</span>{content}</label>;
}
