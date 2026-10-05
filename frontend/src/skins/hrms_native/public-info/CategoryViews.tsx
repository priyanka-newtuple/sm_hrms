import { useMemo } from 'react';
import { CalendarClock, Clock3, Laptop, MapPin, UserRound, UsersRound } from 'lucide-react';
import { AnimIcon, ExternalLinkIcon, PartyPopperIcon } from '../animated-icons';
import { daysUntil, formatDate, formatDay, formatMonth, formatMonthLong, formatWeekday, parseHolidays, safeUrl, splitList, text, toDate, todayIso, type Holiday, type Published } from './format';

function ExternalAction({ url, label }: { url: unknown; label: string }) {
  const href = safeUrl(url);
  if (!href) return null;
  return <a className="hrms-info-action" href={href} target="_blank" rel="noopener noreferrer">{label}<AnimIcon icon={ExternalLinkIcon} size={15} /><span className="sr-only"> (opens in a new tab)</span></a>;
}

function Meta({ icon: Icon, children }: { icon: typeof MapPin; children: React.ReactNode }) {
  return <li><Icon size={15} strokeWidth={1.6} aria-hidden="true" />{children}</li>;
}

/* ── Policies: a readable document list ─────────────────────── */
export function PolicyList({ records }: { records: Published[] }) {
  const sorted = [...records].sort((a, b) => text(b.effective_date).localeCompare(text(a.effective_date)));
  return <ol className="hrms-policy-list">
    {sorted.map(record => {
      const effective = toDate(record.effective_date);
      const body = text(record.body);
      return <li key={record.id} className="hrms-info-card hrms-policy">
        <div className="hrms-policy-head">
          <h3>{text(record.title) || 'Untitled policy'}</h3>
          {effective && <span className="hrms-info-chip">Effective {formatDate(effective)}</span>}
        </div>
        {body && <details className="hrms-policy-body"><summary><span className="hrms-policy-excerpt">{body}</span><span className="hrms-policy-toggle">Read full policy</span></summary><p>{body}</p></details>}
        <ExternalAction url={record.public_url} label="Open policy document" />
      </li>;
    })}
  </ol>;
}

/* ── Learning & development: upcoming and past events ───────── */
function EventCard({ record, past }: { record: Published; past: boolean }) {
  const start = toDate(record.event_date);
  const end = toDate(record.end_date);
  const multiDay = start && end && end.getTime() !== start.getTime();
  return <article className="hrms-info-card hrms-event" data-past={past}>
    <div className="hrms-event-date" aria-hidden="true">{start ? <><b>{formatDay(start)}</b><span>{formatMonth(start)}</span></> : <span>TBA</span>}</div>
    <div className="hrms-event-main">
      <h3>{text(record.title) || 'Learning session'}</h3>
      <ul className="hrms-info-meta">
        {start && <Meta icon={CalendarClock}>{multiDay ? `${formatDate(start)} – ${formatDate(end)}` : formatDate(start)}</Meta>}
        {text(record.trainer) && <Meta icon={UserRound}>{text(record.trainer)}</Meta>}
        {text(record.location) && <Meta icon={MapPin}>{text(record.location)}</Meta>}
      </ul>
      {text(record.body) && <p className="hrms-info-body">{text(record.body)}</p>}
      {!past && <ExternalAction url={record.public_url} label="Register" />}
    </div>
  </article>;
}

export function LearningList({ records }: { records: Published[] }) {
  const today = todayIso();
  const byDate = [...records].sort((a, b) => text(a.event_date).localeCompare(text(b.event_date)));
  const isPast = (r: Published) => (text(r.end_date) || text(r.event_date) || '9999') < today;
  const upcoming = byDate.filter(r => !isPast(r));
  const past = byDate.filter(isPast).reverse();
  return <div className="hrms-event-groups">
    {upcoming.length > 0 && <section aria-label="Upcoming sessions"><h3 className="hrms-info-group">Upcoming</h3><div className="hrms-event-grid">{upcoming.map(r => <EventCard key={r.id} record={r} past={false} />)}</div></section>}
    {past.length > 0 && <section aria-label="Past sessions"><h3 className="hrms-info-group">Past sessions</h3><div className="hrms-event-grid">{past.map(r => <EventCard key={r.id} record={r} past />)}</div></section>}
  </div>;
}

/* ── Holidays: next holiday and the year by month ───────────── */
export function HolidayView({ records }: { records: Published[] }) {
  const calendars = useMemo(() => records.map(record => ({ record, holidays: parseHolidays(record.holidays) }))
    .sort((a, b) => text(b.record.year).localeCompare(text(a.record.year))), [records]);
  const today = todayIso();
  const next = calendars.flatMap(c => c.holidays.map(h => ({ ...h, location: text(c.record.location) })))
    .filter(h => h.iso >= today).sort((a, b) => a.iso.localeCompare(b.iso))[0];

  return <div className="hrms-holidays">
    {next && <div className="hrms-next-holiday" data-anim-trigger>
      <span className="hrms-next-icon"><AnimIcon icon={PartyPopperIcon} size={26} every={5000} /></span>
      <div>
        <p className="hrms-info-group">Next holiday</p>
        <h3>{next.name}</h3>
        <p>{formatWeekday(next.date)}, {formatDate(next.date)}{next.location ? ` · ${next.location}` : ''}</p>
      </div>
      <p className="hrms-next-count"><b>{daysUntil(next.date)}</b><span>{daysUntil(next.date) === 1 ? 'day to go' : 'days to go'}</span></p>
    </div>}
    {calendars.map(({ record, holidays }) => {
      const months = holidays.reduce<Map<string, Holiday[]>>((map, h) => map.set(h.iso.slice(0, 7), [...(map.get(h.iso.slice(0, 7)) ?? []), h]), new Map());
      return <section key={record.id} className="hrms-info-card hrms-calendar" aria-label={text(record.title) || `Holiday calendar ${text(record.year)}`}>
        <header><h3>{text(record.title) || `Holidays ${text(record.year)}`}</h3><ul className="hrms-info-meta">{text(record.year) && <Meta icon={CalendarClock}>{text(record.year)}</Meta>}{text(record.location) && <Meta icon={MapPin}>{text(record.location)}</Meta>}<Meta icon={Clock3}>{holidays.length} {holidays.length === 1 ? 'holiday' : 'holidays'}</Meta></ul></header>
        {text(record.body) && <p className="hrms-info-body">{text(record.body)}</p>}
        <div className="hrms-month-grid">
          {[...months.entries()].map(([month, items]) => <div key={month} className="hrms-month">
            <h4>{formatMonthLong(items[0].date)}</h4>
            <ul>{items.map(h => <li key={h.iso + h.name} data-past={h.iso < today}><span className="hrms-month-day">{formatDay(h.date)}</span><span><b>{h.name}</b><small>{formatWeekday(h.date)}</small></span></li>)}</ul>
          </div>)}
        </div>
        {!holidays.length && <p className="hrms-info-body">No dated holidays in this calendar.</p>}
      </section>;
    })}
  </div>;
}

/* ── Careers: open positions first, then role descriptions ──── */
function RoleCard({ record, opening }: { record: Published; opening: boolean }) {
  const deadline = toDate(record.application_deadline);
  const skills = splitList(record.skills);
  return <article className="hrms-info-card hrms-role">
    <div className="hrms-role-head">
      {text(record.department) && <p className="hrms-info-group">{text(record.department)}</p>}
      <h3>{text(record.title) || 'Role'}</h3>
    </div>
    <ul className="hrms-info-meta">
      {text(record.location) && <Meta icon={MapPin}>{text(record.location)}</Meta>}
      {text(record.work_mode) && <Meta icon={Laptop}>{text(record.work_mode)}</Meta>}
      {opening && text(record.openings) && <Meta icon={UsersRound}>{text(record.openings)} {text(record.openings) === '1' ? 'opening' : 'openings'}</Meta>}
      {opening && deadline && <Meta icon={CalendarClock}>Apply by {formatDate(deadline)}</Meta>}
    </ul>
    {text(record.body) && <p className="hrms-info-body">{text(record.body)}</p>}
    {skills.length > 0 && <ul className="hrms-skill-list" aria-label="Skills">{skills.map(skill => <li key={skill}>{skill}</li>)}</ul>}
    {opening && <ExternalAction url={record.public_url} label="Apply" />}
  </article>;
}

export function CareerList({ records }: { records: Published[] }) {
  const openings = records.filter(r => r.entity_type === 'HRMS.JobOpening');
  const descriptions = records.filter(r => r.entity_type === 'HRMS.JobDescription');
  return <div className="hrms-event-groups">
    {openings.length > 0 && <section aria-label="Open positions"><h3 className="hrms-info-group">Open positions</h3><div className="hrms-role-grid">{openings.map(r => <RoleCard key={r.id} record={r} opening />)}</div></section>}
    {descriptions.length > 0 && <section aria-label="Role descriptions"><h3 className="hrms-info-group">Role descriptions</h3><div className="hrms-role-grid">{descriptions.map(r => <RoleCard key={r.id} record={r} opening={false} />)}</div></section>}
  </div>;
}
