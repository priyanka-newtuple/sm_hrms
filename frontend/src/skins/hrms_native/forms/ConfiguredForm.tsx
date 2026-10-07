import { Children, cloneElement, createContext, isValidElement, useContext, useEffect, type ReactElement, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { request, getApiErrorMessage } from '@/core/services/api/client';

type Field = { field: string; description?: string; placeholder?: string; required?: boolean; read_only?: boolean; col_span?: number; type?: string; enum_values?: string[]; enum_labels?: Record<string,string> };
type Schema = { name: string; fields: Field[] };
const Context = createContext<{ fields: Field[]; aliases: Record<string,string> }>({fields:[],aliases:{}});

export function ConfiguredForm({entityType, aliases = {}, children}: {entityType: string; aliases?: Record<string,string>; children: ReactNode}) {
  const client = useQueryClient();
  const schema = useQuery({queryKey:['hrms','form-config',entityType], queryFn:()=>request<Schema>(`/hrms/forms/${entityType}`), staleTime:0, refetchOnMount:'always'});
  useEffect(() => {
    const refresh = () => { void client.invalidateQueries({queryKey:['hrms','form-config']}); };
    window.addEventListener('form-schemas-changed',refresh);
    return () => window.removeEventListener('form-schemas-changed',refresh);
  },[client]);
  if (schema.isLoading) return <p role="status">Loading form configuration…</p>;
  if (schema.isError) return <p role="alert">{getApiErrorMessage(schema.error)}</p>;
  return <Context.Provider value={{fields:schema.data?.fields??[],aliases}}>{children}</Context.Provider>;
}

/** Keep authorized options and command types; overlay tenant presentation metadata. */
export function ConfiguredField({field, label, children, action, className = 'block space-y-1 text-sm'}: {field:string; label:string; children:ReactNode; action?:ReactNode; className?:string}) {
  const context = useContext(Context);
  const config = context.fields.find(f=>f.field===(context.aliases[field]??field));
  const text = config?.description?.trim() || label;
  const content = Children.map(children, child => {
    if (!isValidElement(child) || !['input','textarea','select'].includes(String(child.type))) return child;
    const control = child as ReactElement<Record<string,unknown>>;
    const props = control.props;
    const select = child.type === 'select';
    const readonly = Boolean(config?.read_only);
    const configured: Record<string,unknown> = {
      required: Boolean(props.required || config?.required),
      placeholder: config?.placeholder ?? props.placeholder,
      readOnly: select ? undefined : Boolean(props.readOnly || readonly),
      disabled: Boolean(props.disabled || (select && readonly)),
    };
    // Fixed enums can be narrowed by config, never extended past the command contract.
    if (select && config?.enum_values?.length && !field.endsWith('_id')) {
      configured.children = Children.toArray(props.children as ReactNode).filter(option => {
        if (!isValidElement(option)) return true;
        const p = option.props as {value?:string; children?:string};
        const value = p.value ?? p.children;
        return !value || config.enum_values!.includes(String(value));
      }).map(option => {
        if (!isValidElement(option)) return option;
        const p = option.props as {value?:string; children?:string};
        const value = String(p.value ?? p.children ?? '');
        return config.enum_labels?.[value] ? cloneElement(option, {}, config.enum_labels[value]) : option;
      });
    }
    return cloneElement(control,configured);
  });
  if (action && !config?.read_only) return <div className={`${className} ${config?.col_span===2?'sm:col-span-2':''}`}><label className="block space-y-1"><span>{text}</span>{content}</label>{action}</div>;
  return <label className={`${className} ${config?.col_span===2?'sm:col-span-2':''}`}><span>{text}</span>{content}</label>;
}
