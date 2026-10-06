import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { request } from '@/core/services/api/client';
import { AnimIcon, ArrowRightIcon, GraduationCapIcon, PartyPopperIcon } from '../animated-icons';
import { daysUntil, formatDate, formatDay, formatMonth, parseHolidays, text, toDate, todayIso, type Published } from '../public-info/format';

type Upcoming = { key: string; kind: 'holiday' | 'learning'; date: Date; title: string; detail: string };

/** Next holidays and learning sessions from HR's published content (same API as Company resources). */
export function ComingUp() {
  const query = useQuery({ queryKey: ['hrms', 'published-content'], queryFn: () => request<Published[]>('/hrms/content') });
  const today = todayIso();
  const items: Upcoming[] = (query.data ?? []).flatMap((record): Upcoming[] => {
    if (record.entity_type === 'HRMS.HolidayCalendar') {
      return parseHolidays(record.holidays).filter(h => h.iso >= today)
        .map(h => ({ key: `${record.id}-${h.iso}-${h.name}`, kind: 'holiday', date: h.date, title: h.name, detail: text(record.location) || 'Holiday' }));
    }
    const start = toDate(record.event_date);
    if (record.entity_type === 'HRMS.LearningEvent' && start && (text(record.end_date) || text(record.event_date)) >= today) {
      return [{ key: record.id, kind: 'learning', date: start, title: text(record.title) || 'Learning session', detail: text(record.trainer) || text(record.location) || 'Learning & development' }];
    }
    return [];
  }).sort((a, b) => a.date.getTime() - b.date.getTime()).slice(0, 4);

  return <section className="hrms-coming" aria-labelledby="hrms-coming-title">
    <header><h2 id="hrms-coming-title">Coming up</h2><Link to="/hrms/content?category=holidays" className="hrms-coming-all">All resources<AnimIcon icon={ArrowRightIcon} size={14} /></Link></header>
    {query.isLoading && <p className="hrms-coming-note" role="status">Loading…</p>}
    {query.isError && <p className="hrms-coming-note" role="alert">Couldn’t load upcoming events. <button type="button" onClick={() => void query.refetch()}>Try again</button></p>}
    {query.isSuccess && !items.length && <p className="hrms-coming-note">Nothing scheduled yet. Holidays and learning sessions appear here once HR publishes them.</p>}
    {items.length > 0 && <ol>
      {items.map(item => {
        const days = daysUntil(item.date);
        return <li key={item.key} data-kind={item.kind}>
          <span className="hrms-coming-date" aria-hidden="true"><b>{formatDay(item.date)}</b>{formatMonth(item.date)}</span>
          <span className="hrms-coming-body"><strong>{item.title}</strong><small>{item.kind === 'holiday' ? <AnimIcon icon={PartyPopperIcon} size={13} /> : <AnimIcon icon={GraduationCapIcon} size={13} />}{item.detail} · {formatDate(item.date)}</small></span>
          <span className="hrms-coming-days">{days === 0 ? 'Today' : days === 1 ? 'Tomorrow' : `in ${days} days`}</span>
        </li>;
      })}
    </ol>}
  </section>;
}
