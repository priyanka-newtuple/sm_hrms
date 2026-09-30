import { CheckCircle2, type LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

/** Shared HRMS inbox presentation; authorization and actions stay with callers. */
export function WorkPanel({ title, description, icon: Icon, count, loading, error, retry, empty, children }: {
  title: string; description: string; icon: LucideIcon; count: number;
  loading: boolean; error?: string; retry: () => void; empty: string; children: ReactNode;
}) {
  return <section className="hrms-work-panel" aria-label={title} aria-busy={loading}>
    <header className="hrms-work-panel-header"><span className="hrms-work-icon"><Icon size={23} strokeWidth={1.25} aria-hidden="true" /></span><div><h2>{title}</h2><p>{description}</p></div>{!loading && !error && <span className="hrms-work-count" aria-label={`${count} available actions`}>{count}</span>}</header>
    {loading ? <p className="hrms-work-feedback" role="status">Loading your actions…</p> : error ? <div className="hrms-work-feedback" role="alert"><p>{error}</p><button className="hrms-outline-button" onClick={retry}>Try again</button></div> : count === 0 ? <div className="hrms-work-empty"><CheckCircle2 size={27} strokeWidth={1.25} aria-hidden="true" /><h3>You’re all caught up</h3><p>{empty}</p></div> : <div className="hrms-work-items">{children}</div>}
  </section>;
}
