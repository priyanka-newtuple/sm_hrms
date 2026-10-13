import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { GraduationCap, PartyPopper } from 'lucide-react';
import { request } from '@/core/services/api/client';
import { AnimIcon, ArrowRightIcon } from '../animated-icons';
import { daysUntil, formatDay, formatMonth, parseHolidays, text, toDate, todayIso, type Published } from '../public-info/format';

type Upcoming = { key: string; kind: 'holiday' | 'learning'; date: Date; title: string; places: string[] };

/** "Pune", "Pune, Mumbai" or "Pune +3": a holiday shared by several offices is listed once. */
const placesLabel = (places: string[]) => (places.length > 2 ? `${places[0]} +${places.length - 1}` : places.join(', '));

/** Next holidays and learning sessions from HR's published content (same API as Company resources). */
export function ComingUp() {
  const query = useQuery({ queryKey: ['hrms', 'published-content'], queryFn: () => request<Published[]>('/hrms/content') });
  const today = todayIso();
  const merged = new Map<string, Upcoming>();
  for (const record of query.data ?? []) {
    if (record.entity_type === 'HRMS.HolidayCalendar') {
      for (const h of parseHolidays(record.holidays).filter(h => h.iso >= today)) {
        const key = `${h.iso}|${h.name}`;
        const place = text(record.location);
        const entry = merged.get(key) ?? { key, kind: 'holiday', date: h.date, title: h.name, places: [] };
        if (place && !entry.places.includes(place)) entry.places.push(place);
        merged.set(key, entry);
      }
    }
    const start = toDate(record.event_date);
    if (record.entity_type === 'HRMS.LearningEvent' && start && (text(record.end_date) || text(record.event_date)) >= today) {
      merged.set(record.id, { key: record.id, kind: 'learning', date: start, title: text(record.title) || 'Learning session', places: [text(record.trainer) || text(record.location) || 'Learning & development'] });
    }
  }
  const items = [...merged.values()].sort((a, b) => a.date.getTime() - b.date.getTime()).slice(0, 6);

  return <section className="hrms-lk-card hrms-coming" aria-labelledby="hrms-coming-title">
    <div className="hrms-lk-card-head"><h2 id="hrms-coming-title">Coming up</h2><Link to="/hrms/content?category=holidays" className="hrms-coming-all">Calendar<AnimIcon icon={ArrowRightIcon} size={14} /></Link></div>
    {query.isLoading && <p className="hrms-coming-note" role="status">Loading…</p>}
    {query.isError && <p className="hrms-coming-note" role="alert">Couldn’t load upcoming events. <button type="button" onClick={() => void query.refetch()}>Try again</button></p>}
    {query.isSuccess && !items.length && <p className="hrms-coming-note">Nothing scheduled yet. Holidays and learning sessions appear here once HR publishes them.</p>}
    {items.length > 0 && <ol>
      {items.map(item => {
        const days = daysUntil(item.date);
        const Icon = item.kind === 'holiday' ? PartyPopper : GraduationCap;
        return <li key={item.key} data-kind={item.kind}>
          <span className="hrms-coming-date" aria-hidden="true"><b>{formatDay(item.date)}</b>{formatMonth(item.date)}</span>
          <span className="hrms-coming-body"><strong>{item.title}</strong><small title={item.places.join(', ')}><Icon size={12} aria-hidden="true" />{placesLabel(item.places)}</small></span>
          <span className="hrms-coming-days">{days === 0 ? 'Today' : days === 1 ? 'Tomorrow' : `${days}d`}</span>
        </li>;
      })}
    </ol>}
  </section>;
}
