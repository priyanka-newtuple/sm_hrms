import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { FileText } from 'lucide-react';
import { request } from '@/core/services/api/client';
import { ContentCard } from './CockpitPage';
import { informationCategories } from '../components/Brand';
export default function PublishedContent({publicPage=false}:{publicPage?:boolean}) {
 const [params,setParams]=useSearchParams();
 const category=informationCategories.find(c=>c.id===params.get('category'))??informationCategories[0];
 const query=useQuery({queryKey:['hrms',publicPage?'public-content':'published-content'],queryFn:()=>publicPage?fetch('/v1/api/hrms/public/content',{credentials:'omit',cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('Unable to load public information');return r.json() as Promise<Record<string,unknown>[]>;}):request<Record<string,unknown>[]>('/hrms/content')});
 const records=query.data?.filter(r=>category.types.includes(String(r.entity_type)))??[];
 return <main className="hrms-information"><p className="hrms-eyebrow">LIFE AT NEWTUPLE</p><h1>Stay informed.<br/><span>Find your next opportunity.</span></h1><p className="hrms-intro">Explore our policies, learning opportunities, holiday calendars, and careers.</p>{publicPage&&<Link className="hrms-outline-button" to="/login">Employee sign in</Link>}
 <nav className="hrms-category-nav" aria-label="Information categories">{informationCategories.map(({id,title,icon:Icon})=><button key={id} aria-pressed={category.id===id} onClick={()=>setParams({category:id})}><Icon size={22} strokeWidth={1.25} aria-hidden="true"/>{title}</button>)}</nav>
 <section aria-labelledby="information-heading" aria-live="polite"><div className="hrms-section-heading"><h2 id="information-heading">{category.title}</h2>{query.isSuccess&&<span>{records.length} published {records.length===1?'item':'items'}</span>}</div>
 {query.isLoading&&<p role="status">Loading published information…</p>}{query.isError&&<div role="alert" className="hrms-empty"><h3>Information couldn’t be loaded</h3><button className="hrms-outline-button" onClick={()=>void query.refetch()}>Try again</button></div>}
 <div className="hrms-published-grid">{records.map(r=><ContentCard key={String(r.id)} item={r}/>)}</div>
 {query.isSuccess&&!records.length&&<div className="hrms-empty"><FileText size={32} strokeWidth={1} aria-hidden="true"/><h3>No {category.title.toLowerCase()} published yet</h3><p>When new information is published{publicPage?' for public viewing':''}, you’ll find it here.</p></div>}</section></main>;
}
