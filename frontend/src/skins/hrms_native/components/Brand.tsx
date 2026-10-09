import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { BookOpen, BriefcaseBusiness, CalendarDays, FileText, Menu, X } from 'lucide-react';
import { MotionConfig } from 'motion/react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { MyHubWordmark } from './MyHubWordmark';
import { BrandWave } from './BrandWave';
import { AnimIcon, ArrowUpRightIcon, BookTextIcon, BriefcaseBusinessIcon, CalendarDaysIcon, CookingPotIcon, FileTextIcon, FolderOpenIcon } from '../animated-icons';

export const informationCategories = [
  { id: 'policies', title: 'Policies', short: 'Policies', description: 'Our policies, clearly explained.', icon: FileText, animatedIcon: FileTextIcon, types: ['HRMS.Policy'] },
  { id: 'learning', title: 'Learning & development', short: 'Learning', description: 'Make room for your next skill.', icon: BookOpen, animatedIcon: BookTextIcon, types: ['HRMS.LearningEvent'] },
  { id: 'holidays', title: 'Holiday calendar', short: 'Holidays', description: 'Plan ahead for the year.', icon: CalendarDays, animatedIcon: CalendarDaysIcon, types: ['HRMS.HolidayCalendar'] },
  { id: 'careers', title: 'Careers', short: 'Careers', description: 'Explore roles and opportunities.', icon: BriefcaseBusiness, animatedIcon: BriefcaseBusinessIcon, types: ['HRMS.JobDescription', 'HRMS.JobOpening'] },
];

/** Other Newtuple tools, opened as plain external links (no session or token is forwarded). */
export const externalResources = [
  { id: 'tiffin', title: 'Tiffin Tuple', description: 'Order meals at the office.', href: 'https://internalapps.newtuple.com/', icon: CookingPotIcon },
  { id: 'templates', title: 'Templates', description: 'Shared document templates.', href: 'https://drive.google.com/drive/folders/17COpLtuSfClDYcWGzLOKYktXLrKF1Pb_', icon: FolderOpenIcon },
];

export function BrandLogo() {
  return <span className="hrms-logo"><img src="/hrms-brand/newtuple-logo.png" alt="Newtuple" /></span>;
}

export function BrandFooter({ compact = false }: { compact?: boolean }) {
  return <footer className={`hrms-brand-footer${compact ? ' hrms-brand-footer--compact' : ''}`}>
    {compact ? <BrandWave /> : <div className="hrms-footer-curves" aria-hidden="true" />}
  </footer>;
}

/**
 * Public header: one quiet bar (brand, text navigation, action). A cobalt underline slides to the
 * hovered or active link; after scrolling the bar turns frosted and tucks away while scrolling down.
 * Below 1000px the navigation moves into a menu sheet.
 */
function PublicHeader() {
  const { pathname, search } = useLocation();
  const active = pathname === '/public' ? new URLSearchParams(search).get('category') ?? 'policies' : null;
  const onLogin = pathname === '/login';
  const [scrolled, setScrolled] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const nav = useRef<HTMLElement>(null);
  const indicator = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    let last = window.scrollY;
    const onScroll = () => {
      const y = window.scrollY;
      setScrolled(y > 24);
      setHidden(y > 320 && y > last + 2);
      if (y < last - 2) setHidden(false);
      last = y;
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') setMenuOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [menuOpen]);

  const moveIndicator = (target: HTMLElement | null) => {
    const pill = indicator.current, host = nav.current;
    if (!pill || !host) return;
    if (!target) { pill.style.opacity = '0'; return; }
    const link = target.getBoundingClientRect(), bar = host.getBoundingClientRect();
    pill.style.opacity = '1';
    pill.style.width = `${link.width}px`;
    pill.style.transform = `translateX(${link.left - bar.left}px)`;
  };
  const restIndicator = () => moveIndicator(nav.current?.querySelector<HTMLElement>('[aria-current="page"]') ?? null);
  useLayoutEffect(restIndicator, [active]);

  const cta = { to: onLogin ? '/public' : '/login', label: onLogin ? 'Explore Newtuple' : 'Employee sign in' };

  return <header className="hrms-pub-header" data-scrolled={scrolled} data-hidden={hidden && !menuOpen}>
    <div className="hrms-pub-bar">
      <div className="hrms-pub-brand">
        <Link to="/login" className="hrms-pub-home" aria-label="Newtuple HRMS home"><BrandLogo /></Link>
        <span className="hrms-pub-myhub"><MyHubWordmark /></span>
      </div>
      <nav ref={nav} className="hrms-pub-links" aria-label="Public information" onMouseLeave={restIndicator} onBlur={restIndicator}>
        <span ref={indicator} className="hrms-nav-indicator" aria-hidden="true" />
        {informationCategories.map(({ id, short }) => <Link key={id} to={`/public?category=${id}`} aria-current={active === id ? 'page' : undefined}
          onMouseEnter={event => moveIndicator(event.currentTarget)} onFocus={event => moveIndicator(event.currentTarget)}>{short}</Link>)}
      </nav>
      <div className="hrms-pub-actions">
        <Link className="hrms-pub-cta" to={cta.to}><span>{cta.label}</span><AnimIcon icon={ArrowUpRightIcon} size={15} /></Link>
        <button type="button" className="hrms-menu-toggle" aria-expanded={menuOpen} aria-controls="hrms-public-menu" aria-label={menuOpen ? 'Close menu' : 'Open menu'} onClick={() => setMenuOpen(open => !open)}>
          {menuOpen ? <X size={18} aria-hidden="true" /> : <Menu size={18} aria-hidden="true" />}
        </button>
      </div>
    </div>
    {menuOpen && <div id="hrms-public-menu" className="hrms-public-menu">
      <nav aria-label="Public information">
        {informationCategories.map(({ id, title }) => <Link key={id} to={`/public?category=${id}`} aria-current={active === id ? 'page' : undefined} onClick={() => setMenuOpen(false)}>{title}<AnimIcon icon={ArrowUpRightIcon} size={16} /></Link>)}
        {externalResources.map(({ id, title, href }) => <a key={id} href={href} target="_blank" rel="noopener noreferrer" onClick={() => setMenuOpen(false)}>{title}<AnimIcon icon={ArrowUpRightIcon} size={16} /><span className="sr-only"> (opens in a new tab)</span></a>)}
      </nav>
      <Link className="hrms-pub-cta" to={cta.to} onClick={() => setMenuOpen(false)}><span>{cta.label}</span><AnimIcon icon={ArrowUpRightIcon} size={15} /></Link>
    </div>}
  </header>;
}

export function PublicLayout() {
  // Animated icons honour the operating-system reduced-motion setting.
  return <MotionConfig reducedMotion="user"><div className="hrms-brand hrms-public-shell"><PublicHeader /><div className="hrms-public-body"><Outlet /></div></div></MotionConfig>;
}

/** Numbered public-information cards; the cobalt fill rises on hover and keyboard focus. */
export function InformationLinks({ includeExternal = true }: { includeExternal?: boolean }) {
  return <nav className="hrms-resource-grid" aria-label="Explore public information">{informationCategories.map(({ id, title, description, animatedIcon }) => <Link className="hrms-resource-card" key={id} to={`/public?category=${id}`}>
    <AnimIcon icon={animatedIcon} className="hrms-card-icon" size={28} />
    <span className="hrms-card-arrow" aria-hidden="true"><AnimIcon icon={ArrowUpRightIcon} size={18} /></span>
    <h3>{title}</h3><p>{description}</p>
  </Link>)}
    {includeExternal && externalResources.map(({ id, title, description, href, icon }) => <a className="hrms-resource-card" key={id} href={href} target="_blank" rel="noopener noreferrer">
    <AnimIcon icon={icon} className="hrms-card-icon" size={28} />
    <span className="hrms-card-arrow" aria-hidden="true"><AnimIcon icon={ArrowUpRightIcon} size={18} /></span>
    <h3>{title}</h3><p>{description}</p><span className="sr-only"> (opens in a new tab)</span>
  </a>)}</nav>;
}
