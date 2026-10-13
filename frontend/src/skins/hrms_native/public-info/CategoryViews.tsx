import { Fragment, useMemo, useState, type ReactNode } from 'react';
import { ChevronRight, ExternalLink, PartyPopper } from 'lucide-react';
import { FilterSelect, ListEmpty, Pager, Segmented, Toolbar } from '../components/ListKit';
import { usePaged } from '../components/useList';
import { daysUntil, formatDate, formatDay, formatMonth, formatMonthLong, formatWeekday, matches, parseHolidays, safeUrl, splitList, text, toDate, todayIso, type Published } from './format';

/**
 * Published HR information as compact, paged lists: one toolbar (search and filters), one line per
 * item, details on demand. Stays short and scannable with hundreds of items, signed in or public.
 */
export interface ViewProps { records: Published[]; search: string; searchField: ReactNode; clearSearch: () => void }

const byText = (a: string, b: string) => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
const unique = (values: string[]) => [...new Set(values.filter(Boolean))].sort(byText);
const allOption = (label: string, values: string[]) => [{ value: '', label }, ...values.map(v => ({ value: v, label: v }))];

function LinkOut({ url, label }: { url: unknown; label: string }) {
  const href = safeUrl(url);
  if (!href) return null;
  return <a className="hrms-lk-link" href={href} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}>
    {label}<ExternalLink size={13} aria-hidden="true" /><span className="sr-only"> (opens in a new tab)</span>
  </a>;
}

function NoResults({ search, clearSearch, reset }: { search: string; clearSearch: () => void; reset?: () => void }) {
  return <ListEmpty title={search ? `No results for “${search}”` : 'Nothing matches these filters'} text="Try a different word or filter."
    action={<button type="button" onClick={() => { clearSearch(); reset?.(); }}>{search ? 'Clear search' : 'Reset filters'}</button>} />;
}

/** One open item at a time; the row and its title button both toggle it. */
function useExpanded() {
  const [open, setOpen] = useState<string | null>(null);
  return { isOpen: (id: string) => open === id, toggle: (id: string) => setOpen(current => (current === id ? null : id)) };
}

function Expander({ id, title, sub, expanded }: { id: string; title: string; sub?: string; expanded: ReturnType<typeof useExpanded> }) {
  return <>
    <button type="button" className="hrms-lk-title" aria-expanded={expanded.isOpen(id)} onClick={e => { e.stopPropagation(); expanded.toggle(id); }}>{title}</button>
    {sub && <span className="hrms-lk-sub">{sub}</span>}
  </>;
}

const Chevron = () => <td className="hrms-lk-end"><span className="hrms-lk-chevron" aria-hidden="true"><ChevronRight size={16} /></span></td>;

/* ── Policies ─────────────────────────────────────────────────── */
export function PolicyList({ records, search, searchField, clearSearch }: ViewProps) {
  const [sort, setSort] = useState('recent');
  const expanded = useExpanded();
  const rows = records.filter(r => matches(r, search)).sort((a, b) => sort === 'title'
    ? byText(text(a.title), text(b.title))
    : text(b.effective_date).localeCompare(text(a.effective_date)));
  const paged = usePaged(rows, 15, `${search}|${sort}`);
  return <div className="hrms-lk-card">
    <Toolbar>{searchField}<FilterSelect label="Sort" value={sort} onChange={setSort} options={[{ value: 'recent', label: 'Newest first' }, { value: 'title', label: 'A–Z' }]} /></Toolbar>
    {rows.length ? <div className="hrms-lk-scroll"><table className="hrms-lk-table">
      <thead><tr><th>Policy</th><th>Effective</th><th><span className="sr-only">Document</span></th><th><span className="sr-only">Details</span></th></tr></thead>
      <tbody>{paged.items.map(record => {
        const effective = toDate(record.effective_date);
        const body = text(record.body);
        return <Fragment key={record.id}>
          <tr data-row data-open={expanded.isOpen(record.id)} onClick={() => expanded.toggle(record.id)} className="cursor-pointer">
            <td><Expander id={record.id} title={text(record.title) || 'Untitled policy'} sub={body} expanded={expanded} /></td>
            <td data-label="Effective" className="hrms-lk-nowrap">{effective ? formatDate(effective) : '—'}</td>
            <td className="hrms-lk-end"><LinkOut url={record.public_url} label="Open document" /></td>
            <Chevron />
          </tr>
          {expanded.isOpen(record.id) && <tr className="hrms-lk-detail"><td colSpan={4}><p>{body || 'No summary was published for this policy. Open the document for the full text.'}</p></td></tr>}
        </Fragment>;
      })}</tbody>
    </table></div> : <NoResults search={search} clearSearch={clearSearch} />}
    <Pager paged={paged} noun="policies" />
  </div>;
}

/* ── Learning & development ───────────────────────────────────── */
export function LearningList({ records, search, searchField, clearSearch }: ViewProps) {
  const today = todayIso();
  const isPast = (r: Published) => (text(r.end_date) || text(r.event_date) || '9999') < today;
  const upcomingCount = records.filter(r => !isPast(r)).length;
  const [when, setWhen] = useState<string | null>(null);
  const view = when ?? (upcomingCount ? 'upcoming' : 'past');
  const [location, setLocation] = useState('');
  const expanded = useExpanded();
  const locations = unique(records.map(r => text(r.location)));
  const rows = records.filter(r => (view === 'past') === isPast(r) && (!location || text(r.location) === location) && matches(r, search))
    .sort((a, b) => (view === 'past' ? -1 : 1) * text(a.event_date).localeCompare(text(b.event_date)));
  const paged = usePaged(rows, 15, `${view}|${location}|${search}`);
  return <div className="hrms-lk-card">
    <Toolbar>
      <Segmented label="When" value={view} onChange={setWhen} segments={[{ id: 'upcoming', label: 'Upcoming', count: upcomingCount }, { id: 'past', label: 'Past', count: records.length - upcomingCount }]} />
      {searchField}
      {locations.length > 1 && <FilterSelect label="Location" value={location} onChange={setLocation} options={allOption('All', locations)} />}
    </Toolbar>
    {rows.length ? <div className="hrms-lk-scroll"><table className="hrms-lk-table">
      <thead><tr><th>Date</th><th>Session</th><th><span className="sr-only">Register</span></th><th><span className="sr-only">Details</span></th></tr></thead>
      <tbody>{paged.items.map(record => {
        const start = toDate(record.event_date);
        const end = toDate(record.end_date);
        const range = start && end && end.getTime() !== start.getTime() ? `${formatDate(start)} – ${formatDate(end)}` : '';
        const sub = [range, text(record.trainer), text(record.location)].filter(Boolean).join(' · ');
        return <Fragment key={record.id}>
          <tr data-row data-past={view === 'past'} data-open={expanded.isOpen(record.id)} onClick={() => expanded.toggle(record.id)} className="cursor-pointer">
            <td className="hrms-lk-nowrap">{start ? <span className="hrms-lk-date"><b>{formatDay(start)} {formatMonth(start)}</b>{formatWeekday(start).slice(0, 3)}</span> : 'TBA'}</td>
            <td><Expander id={record.id} title={text(record.title) || 'Learning session'} sub={sub} expanded={expanded} /></td>
            <td className="hrms-lk-end">{view === 'upcoming' && <LinkOut url={record.public_url} label="Register" />}</td>
            <Chevron />
          </tr>
          {expanded.isOpen(record.id) && <tr className="hrms-lk-detail"><td colSpan={4}><p>{text(record.body) || 'More details will be shared by HR.'}</p></td></tr>}
        </Fragment>;
      })}</tbody>
    </table></div> : search || location ? <NoResults search={search} clearSearch={clearSearch} reset={() => setLocation('')} />
      : <ListEmpty title={view === 'upcoming' ? 'No upcoming sessions' : 'No past sessions'} text={view === 'upcoming' ? 'New sessions will appear here when HR publishes them.' : undefined} />}
    <Pager paged={paged} noun={view === 'upcoming' ? 'upcoming sessions' : 'past sessions'} />
  </div>;
}

/* ── Holidays: one calendar at a time, by location and year ───── */
const LOCATION_KEY = 'hrms.holiday-location';
const remembered = () => { try { return localStorage.getItem(LOCATION_KEY) ?? ''; } catch { return ''; } };

export function HolidayView({ records, search, searchField, clearSearch }: ViewProps) {
  const today = todayIso();
  const holidays = useMemo(() => records.flatMap(record => parseHolidays(record.holidays).map(h => ({ ...h, year: text(record.year) || h.iso.slice(0, 4), location: text(record.location) || 'All offices', calendar: record.id }))), [records]);
  const years = unique(holidays.map(h => h.year)).reverse();
  const [yearChoice, setYear] = useState('');
  const year = years.includes(yearChoice) ? yearChoice : years.includes(today.slice(0, 4)) ? today.slice(0, 4) : years[0] ?? '';
  const locations = unique(holidays.filter(h => h.year === year).map(h => h.location));
  const [locationChoice, setLocationChoice] = useState(remembered);
  const location = locationChoice === 'all' || locations.includes(locationChoice) ? locationChoice : locations[0] ?? 'all';
  const chooseLocation = (value: string) => { setLocationChoice(value); try { localStorage.setItem(LOCATION_KEY, value); } catch { /* storage unavailable */ } };
  const [range, setRange] = useState('year');
  const inScope = holidays.filter(h => h.year === year && (location === 'all' || h.location === location));
  const next = inScope.filter(h => h.iso >= today).sort((a, b) => a.iso.localeCompare(b.iso))[0];
  const rows = inScope.filter(h => (range === 'year' || h.iso >= today) && (!search || `${h.name} ${h.location}`.toLowerCase().includes(search.toLowerCase())))
    .sort((a, b) => a.iso.localeCompare(b.iso) || byText(a.location, b.location));
  const paged = usePaged(rows, 40, `${year}|${location}|${range}|${search}`);
  const showLocation = location === 'all';
  const notes = location === 'all' ? '' : text(records.find(r => text(r.location) === location && text(r.year) === year)?.body);
  return <div className="hrms-lk-card">
    <Toolbar end={<Segmented label="Range" value={range} onChange={setRange} segments={[{ id: 'year', label: 'Full year' }, { id: 'upcoming', label: 'Upcoming' }]} />}>
      {searchField}
      {locations.length > 1 && <FilterSelect label="Location" value={location} onChange={chooseLocation} options={[...locations.map(l => ({ value: l, label: l })), { value: 'all', label: 'All locations' }]} />}
      {years.length > 1 && <FilterSelect label="Year" value={year} onChange={setYear} options={years.map(y => ({ value: y, label: y }))} />}
    </Toolbar>
    {next && <p className="hrms-next-line"><PartyPopper size={16} aria-hidden="true" /><span>Next holiday</span><b>{next.name}</b>{formatWeekday(next.date)}, {formatDate(next.date)}{showLocation ? ` · ${next.location}` : ''}<span className="hrms-lk-tag">{daysUntil(next.date) === 0 ? 'Today' : `in ${daysUntil(next.date)} ${daysUntil(next.date) === 1 ? 'day' : 'days'}`}</span></p>}
    {notes && <p className="hrms-holiday-notes">{notes}</p>}
    {rows.length ? <div className="hrms-lk-scroll"><table className="hrms-lk-table hrms-holiday-table">
      <thead><tr><th>Date</th><th>Day</th><th>Holiday</th>{showLocation && <th>Location</th>}</tr></thead>
      <tbody>{paged.items.map((h, i) => {
        const month = h.iso.slice(0, 7);
        const newMonth = i === 0 || paged.items[i - 1].iso.slice(0, 7) !== month;
        return <Fragment key={`${h.calendar}-${h.iso}-${h.name}`}>
          {newMonth && <tr className="hrms-lk-group"><td colSpan={showLocation ? 4 : 3}>{formatMonthLong(h.date)}</td></tr>}
          <tr data-row data-past={h.iso < today}>
            <td className="hrms-lk-nowrap"><span className="hrms-lk-date"><b>{formatDay(h.date)} {formatMonth(h.date)}</b></span></td>
            <td>{formatWeekday(h.date)}</td>
            <td><span className="hrms-lk-title">{h.name}</span>{h === next && <span className="hrms-lk-tag" data-tone="soon">Next</span>}</td>
            {showLocation && <td data-label="Location">{h.location}</td>}
          </tr>
        </Fragment>;
      })}</tbody>
    </table></div> : search ? <NoResults search={search} clearSearch={clearSearch} />
      : <ListEmpty title={range === 'upcoming' ? 'No more holidays this year' : 'No holidays in this calendar'} action={range === 'upcoming' ? <button type="button" onClick={() => setRange('year')}>Show the full year</button> : undefined} />}
    <Pager paged={paged} noun="holidays" />
  </div>;
}

/* ── Careers: open positions and role descriptions ────────────── */
export function CareerList({ records, search, searchField, clearSearch }: ViewProps) {
  const openings = records.filter(r => r.entity_type === 'HRMS.JobOpening');
  const descriptions = records.filter(r => r.entity_type === 'HRMS.JobDescription');
  const [tab, setTab] = useState<string | null>(null);
  const view = tab ?? (openings.length || !descriptions.length ? 'openings' : 'roles');
  const source = view === 'openings' ? openings : descriptions;
  const [department, setDepartment] = useState('');
  const [location, setLocation] = useState('');
  const [mode, setMode] = useState('');
  const expanded = useExpanded();
  const departments = unique(source.map(r => text(r.department)));
  const locations = unique(source.map(r => text(r.location)));
  const modes = unique(source.map(r => text(r.work_mode)));
  const rows = source.filter(r => (!department || text(r.department) === department) && (!location || text(r.location) === location) && (!mode || text(r.work_mode) === mode) && matches(r, search))
    .sort((a, b) => view === 'openings' ? (text(a.application_deadline) || '9999').localeCompare(text(b.application_deadline) || '9999') || byText(text(a.title), text(b.title)) : byText(text(a.title), text(b.title)));
  const paged = usePaged(rows, 15, `${view}|${department}|${location}|${mode}|${search}`);
  const reset = () => { setDepartment(''); setLocation(''); setMode(''); };
  const choose = (id: string) => { setTab(id); reset(); };
  const columns = view === 'openings' ? 7 : 3;
  return <div className="hrms-lk-card">
    <Toolbar>
      <Segmented label="Careers" value={view} onChange={choose} segments={[{ id: 'openings', label: 'Open positions', count: openings.length }, { id: 'roles', label: 'Role descriptions', count: descriptions.length }]} />
      {searchField}
      {departments.length > 1 && <FilterSelect label="Team" value={department} onChange={setDepartment} options={allOption('All', departments)} />}
      {view === 'openings' && locations.length > 1 && <FilterSelect label="Location" value={location} onChange={setLocation} options={allOption('All', locations)} />}
      {view === 'openings' && modes.length > 1 && <FilterSelect label="Mode" value={mode} onChange={setMode} options={allOption('All', modes)} />}
    </Toolbar>
    {rows.length ? <div className="hrms-lk-scroll"><table className="hrms-lk-table">
      <thead><tr><th>Role</th>{view === 'openings' ? <><th>Location</th><th>Mode</th><th>Openings</th><th>Apply by</th><th><span className="sr-only">Apply</span></th></> : <th>Skills</th>}<th><span className="sr-only">Details</span></th></tr></thead>
      <tbody>{paged.items.map(record => {
        const deadline = toDate(record.application_deadline);
        const skills = splitList(record.skills);
        return <Fragment key={record.id}>
          <tr data-row data-open={expanded.isOpen(record.id)} onClick={() => expanded.toggle(record.id)} className="cursor-pointer">
            <td><Expander id={record.id} title={text(record.title) || 'Role'} sub={text(record.department)} expanded={expanded} /></td>
            {view === 'openings' ? <>
              <td data-label="Location">{text(record.location) || '—'}</td>
              <td data-label="Mode">{text(record.work_mode) || '—'}</td>
              <td data-label="Openings" className="hrms-lk-nowrap">{text(record.openings) || '—'}</td>
              <td data-label="Apply by" className="hrms-lk-nowrap">{deadline ? formatDate(deadline) : '—'}</td>
              <td className="hrms-lk-end"><LinkOut url={record.public_url} label="Apply" /></td>
            </> : <td data-label="Skills"><ul className="hrms-lk-chips" aria-label="Skills">{skills.slice(0, 3).map(s => <li key={s}>{s}</li>)}{skills.length > 3 && <li>+{skills.length - 3}</li>}</ul></td>}
            <Chevron />
          </tr>
          {expanded.isOpen(record.id) && <tr className="hrms-lk-detail"><td colSpan={columns}>
            <p>{text(record.body) || 'Details will be shared during the hiring process.'}</p>
            {skills.length > 0 && <ul className="hrms-lk-chips" aria-label="Skills">{skills.map(s => <li key={s}>{s}</li>)}</ul>}
          </td></tr>}
        </Fragment>;
      })}</tbody>
    </table></div> : search || department || location || mode ? <NoResults search={search} clearSearch={clearSearch} reset={reset} />
      : <ListEmpty title={view === 'openings' ? 'No open positions right now' : 'No role descriptions yet'} text="Check back soon." />}
    <Pager paged={paged} noun={view === 'openings' ? 'open positions' : 'role descriptions'} />
  </div>;
}
