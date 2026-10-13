import type { ComponentType, ReactNode } from 'react';
import { ChevronDown, ChevronLeft, ChevronRight, Search, X } from 'lucide-react';
import type { Paged } from './useList';
import './list-kit.css';

/**
 * Small building blocks for long lists, shared by the HR Cockpit and the published information pages
 * (signed in and public): one toolbar row, a compact table and a pager, so 50+ items stay findable
 * without endless scrolling and every list in the HRMS behaves the same way.
 */

/** Page numbers around the current page, with gaps: 1 … 4 5 6 … 12. */
function pageList(page: number, pages: number) {
  const wanted = new Set([0, pages - 1, page - 1, page, page + 1].filter(p => p >= 0 && p < pages));
  const sorted = [...wanted].sort((a, b) => a - b);
  return sorted.flatMap((p, i) => (i > 0 && p - sorted[i - 1] > 1 ? ['gap' as const, p] : [p]));
}

export function Pager<T>({ paged, noun }: { paged: Paged<T>; noun: string }) {
  if (!paged.total) return null;
  const first = paged.page * paged.size + 1;
  const last = Math.min(paged.total, first + paged.size - 1);
  return <nav className="hrms-lk-pager" aria-label={`${noun} pages`}>
    <p aria-live="polite">{paged.pages > 1 ? <>Showing <b>{first}–{last}</b> of <b>{paged.total}</b> {noun}</> : <><b>{paged.total}</b> {noun}</>}</p>
    {paged.pages > 1 && <div className="hrms-lk-pages">
      <button type="button" onClick={() => paged.setPage(paged.page - 1)} disabled={paged.page === 0} aria-label="Previous page"><ChevronLeft size={15} aria-hidden="true" /></button>
      {pageList(paged.page, paged.pages).map((p, i) => p === 'gap'
        ? <span key={`gap-${i}`} aria-hidden="true">…</span>
        : <button key={p} type="button" onClick={() => paged.setPage(p)} aria-current={p === paged.page ? 'page' : undefined} aria-label={`Page ${p + 1}`}>{p + 1}</button>)}
      <button type="button" onClick={() => paged.setPage(paged.page + 1)} disabled={paged.page >= paged.pages - 1} aria-label="Next page"><ChevronRight size={15} aria-hidden="true" /></button>
    </div>}
  </nav>;
}

export function SearchField({ value, onChange, placeholder }: { value: string; onChange: (value: string) => void; placeholder: string }) {
  return <label className="hrms-lk-search">
    <span className="sr-only">{placeholder}</span>
    <Search size={15} aria-hidden="true" />
    <input type="search" value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} />
    {value && <button type="button" onClick={() => onChange('')} aria-label="Clear search"><X size={14} aria-hidden="true" /></button>}
  </label>;
}

export interface Option { value: string; label: string }

export function FilterSelect({ label, value, options, onChange }: { label: string; value: string; options: Option[]; onChange: (value: string) => void }) {
  return <label className="hrms-lk-select" data-active={value !== options[0]?.value || undefined}>
    <span>{label}</span>
    <select value={value} onChange={e => onChange(e.target.value)}>{options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
    <ChevronDown size={14} aria-hidden="true" />
  </label>;
}

export interface Segment { id: string; label: string; count?: number; icon?: ComponentType<{ size?: number; 'aria-hidden'?: boolean }>; badge?: string }

/** One row of mutually exclusive views (categories, upcoming/past…), with optional counts; empty ones are muted. */
export function Segmented({ segments, value, onChange, label, variant = 'pill' }: { segments: Segment[]; value: string; onChange: (id: string) => void; label: string; variant?: 'pill' | 'underline' }) {
  return <div className={`hrms-lk-seg hrms-lk-seg--${variant}`} role="group" aria-label={label}>
    {segments.map(({ id, label: text, count, icon: Icon, badge }) => <button key={id} type="button" aria-pressed={value === id} data-empty={count === 0 || undefined} onClick={() => onChange(id)}>
      {Icon && <Icon size={15} aria-hidden={true} />}{text}
      {count !== undefined && count > 0 && <span className="hrms-lk-count">{count}</span>}
      {badge && <span className="hrms-lk-badge">{badge}</span>}
    </button>)}
  </div>;
}

export function Toolbar({ children, end }: { children: ReactNode; end?: ReactNode }) {
  return <div className="hrms-lk-toolbar">{children}{end && <div className="hrms-lk-toolbar-end">{end}</div>}</div>;
}

export function ListEmpty({ title, text, action }: { title: string; text?: string; action?: ReactNode }) {
  return <div className="hrms-lk-empty"><h3>{title}</h3>{text && <p>{text}</p>}{action}</div>;
}
