import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { request, getApiErrorMessage } from '@/core/services/api/client';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { useHrmsCapabilities } from '../capabilities';
import { PageHero } from '../components/PageHero';
import { ProjectAction } from './ProjectsPage';
type Customer = {id:string;name:string;contact_name?:string;contact_email?:string;currency?:string};
export default function CustomersPage() {
 const caps=useHrmsCapabilities();
 const allowed=caps.data?.capabilities.includes('project:view')??false;
 const [search,setSearch]=useState('');
 const [creating,setCreating]=useState(false);
 const query=useQuery({queryKey:['hrms','customers'],queryFn:()=>request<{items:Customer[];can_create:boolean}>('/hrms/customers'),enabled:allowed});
 if(caps.isLoading)return <p role="status">Loading customer access…</p>;
 if(caps.isError)return <div role="alert">Could not load access. <button onClick={()=>void caps.refetch()}>Retry</button></div>;
 if(!allowed)return <p role="alert">Customers are not available to your role.</p>;
 const items=query.data?.items.filter(c=>[c.name,c.contact_name,c.contact_email].join(' ').toLowerCase().includes(search.toLowerCase()))??[];
 return <main className="hrms-workspace-page"><PageHero title="Customers" intro="Customer contacts for your projects and delivery." illustration="projects" actions={query.data?.can_create&&<button className="hrms-primary-button" onClick={()=>setCreating(true)}>Add customer</button>} stats={query.data?[{label:'Customers',value:query.data.items.length}]:undefined}/>
 <div className="hrms-filter-bar"><input aria-label="Search customers" className="hrms-field-input" placeholder="Search customer or contact…" value={search} onChange={e=>setSearch(e.target.value)}/></div>
 {query.isLoading&&<p role="status">Loading customers…</p>}
 {query.isError&&<div role="alert" className="hrms-notice hrms-notice--error">{getApiErrorMessage(query.error)} <button onClick={()=>void query.refetch()}>Retry</button></div>}
 {query.isSuccess&&<section className="hrms-surface hrms-directory"><div className="hrms-directory-heading"><h2 className="hrms-section-heading">Customer directory</h2></div><div className="hrms-table-scroll"><table className="hrms-people-table"><thead><tr>{['Customer','Contact name','Contact email','Currency'].map(h=><th className="p-3 text-left" key={h}>{h}</th>)}</tr></thead><tbody>{items.map(c=><tr key={c.id} className="border-t border-slate-100"><td className="p-3 font-semibold">{c.name}</td><td className="p-3">{c.contact_name||'—'}</td><td className="p-3">{c.contact_email||'—'}</td><td className="p-3">{c.currency||'—'}</td></tr>)}{!items.length&&<tr><td colSpan={4} className="hrms-empty-message">{search?'No customers match your search.':'No customers available in your scope yet.'}</td></tr>}</tbody></table></div></section>}
 <Sheet open={creating} onOpenChange={setCreating}><SheetContent className="hrms-brand hrms-review-drawer overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-4xl"><SheetHeader><SheetTitle>Add customer</SheetTitle></SheetHeader>{creating&&<ProjectAction action="create_customer" done={()=>setCreating(false)}/>}</SheetContent></Sheet></main>;
}
