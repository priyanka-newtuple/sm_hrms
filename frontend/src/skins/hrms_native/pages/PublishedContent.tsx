import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { request } from '@/core/services/api/client';
import { ContentCard, CONTENT_TYPES, CONTENT_LABELS } from './CockpitPage';
export default function PublishedContent({publicPage=false}:{publicPage?:boolean}) {
 const [kind,setKind]=useState('');
 const query=useQuery({queryKey:['hrms',publicPage?'public-content':'published-content'],queryFn:()=>publicPage?fetch('/v1/api/hrms/public/content',{credentials:'omit',cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('Unable to load public information');return r.json() as Promise<Record<string,unknown>[]>;}):request<Record<string,unknown>[]>('/hrms/content')});
 return <section className="mx-auto max-w-6xl space-y-5 p-6"><h2 className="text-2xl font-semibold">Newtuple information</h2><p>{publicPage?'Public announcements, learning events, holidays and careers.':'Published policies, calendars and careers.'}</p>{publicPage&&<Link className="text-blue-700 underline" to="/login">Employee sign in</Link>}<select aria-label="Content category" className="rounded-lg border p-2" value={kind} onChange={e=>setKind(e.target.value)}><option value="">All information</option>{CONTENT_TYPES.map((t,i)=><option key={t} value={t}>{CONTENT_LABELS[i]}</option>)}</select>{query.isLoading&&<p>Loading information…</p>}{query.isError&&<p role="alert">Unable to load published information. Please try again later.</p>}<div className="grid gap-4 md:grid-cols-2">{query.data?.filter(r=>!kind||r.entity_type===kind).map(r=><ContentCard key={String(r.id)} item={r}/>)}</div>{query.data&&!query.data.some(r=>!kind||r.entity_type===kind)&&<p>No published information in this section yet.</p>}</section>;
}
