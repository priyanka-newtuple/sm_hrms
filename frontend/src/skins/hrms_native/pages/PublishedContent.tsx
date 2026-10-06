import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { X } from 'lucide-react';
import { request } from '@/core/services/api/client';
import { informationCategories } from '../components/Brand';
import { AnimIcon, ArrowRightIcon, SearchIcon } from '../animated-icons';
import { Waves } from '../login/Waves';
import { usePrefersReducedMotion } from '../components/useReducedMotion';
import { CareerList, HolidayView, LearningList, PolicyList } from '../public-info/CategoryViews';
import { matches, type Published } from '../public-info/format';
import '../login/login.css';
import '../public-info/public-info.css';

const VIEWS = { policies: PolicyList, learning: LearningList, holidays: HolidayView, careers: CareerList } as const;

/** Published HR information: public at /public, and for signed-in employees at /hrms/content. */
export default function PublishedContent({ publicPage = false }: { publicPage?: boolean }) {
  const [params, setParams] = useSearchParams();
  const reducedMotion = usePrefersReducedMotion();
  const motion = !reducedMotion;
  const [search, setSearch] = useState('');
  const tabs = useRef<HTMLDivElement>(null);

  const categoryIndex = Math.max(0, informationCategories.findIndex(c => c.id === params.get('category')));
  const category = informationCategories[categoryIndex];
  const query = useQuery({
    queryKey: ['hrms', publicPage ? 'public-content' : 'published-content'],
    queryFn: () => publicPage
      ? fetch('/v1/api/hrms/public/content', { credentials: 'omit', cache: 'no-store' }).then(r => { if (!r.ok) throw new Error('Unable to load public information'); return r.json() as Promise<Published[]>; })
      : request<Published[]>('/hrms/content'),
  });

  const counts = useMemo(() => Object.fromEntries(informationCategories.map(c => [c.id, query.data?.filter(r => c.types.includes(String(r.entity_type))).length ?? 0])), [query.data]);
  const inCategory = query.data?.filter(r => category.types.includes(String(r.entity_type))) ?? [];
  const records = inCategory.filter(r => matches(r, search.trim()));
  const View = VIEWS[category.id as keyof typeof VIEWS];

  const choose = (id: string) => { setSearch(''); setParams({ category: id }); };

  // Slide the white pill to the pressed tab; tabs can scroll horizontally on narrow screens.
  useLayoutEffect(() => {
    const host = tabs.current;
    if (!host) return;
    const place = () => {
      const pressed = host.querySelector<HTMLElement>('button[aria-pressed="true"]');
      if (!pressed) return;
      host.style.setProperty('--tab-x', `${pressed.offsetLeft}px`);
      host.style.setProperty('--tab-w', `${pressed.offsetWidth}px`);
      if (host.scrollWidth > host.clientWidth) host.scrollTo({ left: pressed.offsetLeft - (host.clientWidth - pressed.offsetWidth) / 2, behavior: 'auto' });
    };
    place();
    const observer = new ResizeObserver(place);
    observer.observe(host);
    return () => observer.disconnect();
  }, [categoryIndex, query.isSuccess]);

  return <main className={`hrms-login hrms-info${publicPage ? '' : ' hrms-info--workspace'}${motion ? ' hrms-login--motion' : ''}`}>
    <section className="hrms-info-hero">
      <Waves animate={motion} className="hrms-info-waves" />
      <div className="hrms-info-hero-inner">
        <h1>Stay informed. <span>Find your next opportunity.</span></h1>
        <p className="hrms-info-intro">Policies, learning, holidays and open roles — published by HR{publicPage ? ', readable without signing in' : ''}.</p>
        {/* The public header already lists the categories; only the signed-in page needs this switcher. */}
        {!publicPage && <div ref={tabs} className="hrms-info-tabs" role="group" aria-label="Information categories">
          <span className="hrms-info-tab-indicator" aria-hidden="true" />
          {informationCategories.map(({ id, short, animatedIcon }) => <button key={id} type="button" aria-pressed={category.id === id} onClick={() => choose(id)}>
            <AnimIcon icon={animatedIcon} size={18} />{short}
            {query.isSuccess && <span className="hrms-info-tab-count" aria-label={`${counts[id]} published`}>{counts[id]}</span>}
          </button>)}
        </div>}
      </div>
    </section>

    <section className="hrms-info-content" aria-labelledby="information-heading">
      <header className="hrms-info-head">
        <div>
          <p className="hrms-index-label">{category.short}</p>
          <h2 id="information-heading">{category.title}</h2>
          <p>{category.description}</p>
        </div>
        <label className="hrms-info-search">
          <span className="sr-only">Search {category.title.toLowerCase()}</span>
          <AnimIcon icon={SearchIcon} size={17} />
          <input type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder={`Search ${category.short.toLowerCase()}`} />
          {search && <button type="button" onClick={() => setSearch('')} aria-label="Clear search"><X size={15} aria-hidden="true" /></button>}
        </label>
      </header>

      <div aria-live="polite">
        {query.isSuccess && <p className="hrms-info-count">{search ? `${records.length} of ${inCategory.length}` : inCategory.length} published {inCategory.length === 1 ? 'item' : 'items'}</p>}
        {query.isLoading && <div className="hrms-info-skeletons" role="status" aria-label="Loading published information">{[0, 1, 2].map(i => <div key={i} className="hrms-info-skeleton" />)}</div>}
        {query.isError && <div role="alert" className="hrms-info-empty"><h3>Information couldn’t be loaded</h3><p>Check your connection and try again.</p><button type="button" className="hrms-info-action" onClick={() => void query.refetch()}>Try again</button></div>}
        {query.isSuccess && records.length > 0 && <div key={category.id} className="hrms-info-view"><View records={records} /></div>}
        {query.isSuccess && !records.length && (search
          ? <div className="hrms-info-empty"><h3>No results for “{search}”</h3><p>Try a different word, or clear the search.</p><button type="button" className="hrms-info-action" onClick={() => setSearch('')}>Clear search</button></div>
          : <div className="hrms-info-empty" data-anim-trigger>
              <span className="hrms-info-empty-icon"><AnimIcon icon={category.animatedIcon} size={30} every={motion ? 4000 : undefined} /></span>
              <h3>No {category.title.toLowerCase()} published yet</h3>
              <p>When HR publishes something{publicPage ? ' for public viewing' : ''}, you’ll find it here.{publicPage ? ' Employees may see more after signing in.' : ''}</p>
              {publicPage && <Link to="/login" className="hrms-info-action">Employee sign in<AnimIcon icon={ArrowRightIcon} size={15} /></Link>}
            </div>)}
      </div>
    </section>
  </main>;
}
