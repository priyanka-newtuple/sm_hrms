import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Mail, RefreshCw, Download } from 'lucide-react';
import { request } from '@/core/services/api/client';
import { useHrmsCapabilities } from '../capabilities';

type Address = { Name?: string; Address: string };
type Message = { ID: string; Subject: string; Created: string; From: Address; To: Address[]; Cc?: Address[]; Bcc?: Address[]; Text?: string; HTML?: string; Attachments?: { PartID: string; FileName: string }[] };
const addresses = (items?: Address[]) => (items || []).map(item => item.Address).join(', ');

function useInboxStatus() {
  const caps = useHrmsCapabilities();
  return useQuery({ queryKey: ['hrms', 'uat-mail', 'status', caps.data?.roles], queryFn: () => request<{ enabled: boolean }>('/hrms/uat-mail/status'), enabled: Boolean(caps.data), staleTime: 0, gcTime: 0, refetchInterval: 30000 });
}

export function UatInboxLink() {
  const status = useInboxStatus();
  return status.data?.enabled ? <Link className="hrms-text-link inline-flex items-center gap-2 my-3" to="/hrms/uat-inbox"><Mail size={18}/>UAT email inbox</Link> : null;
}

export default function UatInbox() {
  const status = useInboxStatus();
  const [start, setStart] = useState(0);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState('');
  const [error, setError] = useState('');
  const list = useQuery({ queryKey: ['hrms', 'uat-mail', 'messages', start, search], queryFn: () => request<{ messages: Message[]; total: number; messages_count?: number }>(`/hrms/uat-mail/messages?start=${start}&search=${encodeURIComponent(search)}`), enabled: status.data?.enabled === true, gcTime: 0 });
  const detail = useQuery({ queryKey: ['hrms', 'uat-mail', selected], queryFn: () => request<Message>(`/hrms/uat-mail/messages/${encodeURIComponent(selected)}`), enabled: status.data?.enabled === true && Boolean(selected), gcTime: 0 });
  async function download(part: { PartID: string; FileName: string }) {
    setError('');
    try {
      const data = await request<{ content: string }>(`/hrms/uat-mail/messages/${encodeURIComponent(selected)}/attachments/${encodeURIComponent(part.PartID)}`);
      const url = URL.createObjectURL(new Blob([Uint8Array.from(atob(data.content), char => char.charCodeAt(0))], { type: 'application/octet-stream' }));
      const link = document.createElement('a'); link.href = url; link.download = part.FileName.replace(/[\\/]/g, '_'); link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setError('Could not download the attachment. Please retry.'); }
  }
  if (status.isPending) return <p role="status" className="p-6">Checking inbox access…</p>;
  if (status.isError) return <p role="alert" className="p-6">Could not check inbox access. <button onClick={() => void status.refetch()}>Retry</button></p>;
  if (!status.data.enabled) return <p className="p-6">UAT email inbox is not available. <Link to="/hrms/cockpit">Back to HR Cockpit</Link></p>;
  return <main className="hrms-workspace-page">
    <Link className="hrms-text-link" to="/hrms/cockpit">← HR Cockpit</Link>
    <section className="hrms-surface p-6">
      <h1 className="text-2xl font-light">UAT email inbox</h1>
      <p className="mt-2 text-slate-600">Captured test emails — not delivered to recipients. This shared inbox includes emails for all test users.</p>
      <div className="flex gap-3 my-4"><input aria-label="Search test emails" placeholder="Search emails, or use to:email@example.com" className="rounded-xl border p-3 flex-1" value={search} onChange={event => { setSearch(event.target.value); setStart(0); setSelected(''); }}/><button className="hrms-text-link inline-flex gap-2 items-center" onClick={() => { void list.refetch(); if (selected) void detail.refetch(); }}><RefreshCw size={18}/>Refresh</button></div>
      {list.isPending ? <p role="status">Loading emails…</p> : list.isError ? <p role="alert">Could not load emails. <button onClick={() => void list.refetch()}>Retry</button></p> : <>
        {!list.data.messages.length ? <p>No emails match this view.</p> : <ul className="divide-y">{list.data.messages.map(message => <li key={message.ID}><button className="text-left w-full p-3 rounded-xl hover:bg-blue-50" onClick={() => setSelected(message.ID)}><strong>{message.Subject || '(No subject)'}</strong><p className="text-sm text-slate-600">To: {addresses(message.To)} · {new Date(message.Created).toLocaleString()}</p></button></li>)}</ul>}
        <div className="flex gap-4 mt-4"><button disabled={!start} onClick={() => setStart(Math.max(0, start - 50))}>Previous</button><span>Page {Math.floor(start / 50) + 1}</span><button disabled={start + 50 >= (list.data.messages_count ?? list.data.total)} onClick={() => setStart(start + 50)}>Next</button></div>
      </>}
    </section>
    {selected && <section className="hrms-surface p-6">{detail.isPending ? <p role="status">Loading email…</p> : detail.isError ? <p role="alert">Could not load this email. <button onClick={() => void detail.refetch()}>Retry</button></p> : detail.data && <>
      <h2 className="text-lg font-semibold">{detail.data.Subject}</h2><p>From: {detail.data.From?.Address}</p><p>To: {addresses(detail.data.To)}</p>{detail.data.Cc?.length ? <p>Cc: {addresses(detail.data.Cc)}</p> : null}{detail.data.Bcc?.length ? <p>Bcc: {addresses(detail.data.Bcc)}</p> : null}
      <p className="my-3 text-sm text-slate-600">Use the intended test account when following an email link. Reading an email does not complete its task.</p>
      {detail.data.HTML ? <iframe title="Email preview" sandbox="allow-popups allow-popups-to-escape-sandbox" referrerPolicy="no-referrer" className="w-full min-h-[450px] border rounded-xl" srcDoc={'<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'"><base target="_blank">' + detail.data.HTML}/> : <pre className="whitespace-pre-wrap font-sans">{detail.data.Text}</pre>}
      {(detail.data.Attachments || []).map(part => <button key={part.PartID} className="hrms-text-link inline-flex gap-2 m-3" onClick={() => void download(part)}><Download size={18}/>{part.FileName}</button>)}{error && <p role="alert">{error}</p>}
    </>}</section>}
  </main>;
}
