import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { ChevronDown, CornerDownLeft, LogOut } from 'lucide-react';
import { useAuth } from '../../../core/auth';
import { useHrmsCapabilities } from '../capabilities';
import TenantHeader from '../components/TenantHeader';
import { Illustration } from '../components/Illustration';
import { usePrefersReducedMotion } from '../components/useReducedMotion';
import {
  AnimIcon, BellIcon, BookTextIcon, BriefcaseBusinessIcon, CalendarDaysIcon, LayoutGridIcon, MenuIcon, PanelLeftCloseIcon,
  PanelLeftOpenIcon, SearchIcon, SettingsIcon, SlidersHorizontalIcon, TrendingUpIcon, UsersIcon,
  XIcon, ZapIcon, type AnimatedIcon,
} from '../animated-icons';
import { useWaitingActions, type WaitingSource } from './useWaitingActions';

interface NavItem { path: string; label: string; icon: AnimatedIcon; badge?: number; keywords?: string; comingSoon?: boolean }
interface NavGroup { label: string; standalone?: boolean; items: NavItem[] }

const COLLAPSE_KEY = 'hrms.sidebar.collapsed';
const readCollapsed = () => { try { return localStorage.getItem(COLLAPSE_KEY) === '1'; } catch { return false; } };
const roleName = (role: string) => role === 'superadmin' ? 'Super Admin' : role.replace(/^hrms_/, '').replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());

/** Closes a popover on outside click or Escape and returns focus to its trigger. */
function useDismiss(open: boolean, close: () => void, root: RefObject<HTMLElement | null>, trigger: RefObject<HTMLElement | null>) {
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) close(); };
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') { close(); trigger.current?.focus(); } };
    document.addEventListener('pointerdown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('pointerdown', onPointer); document.removeEventListener('keydown', onKey); };
  }, [open, close, root, trigger]);
}

/* ── Sidebar ───────────────────────────────────────────────── */
function Sidebar({ groups, settings, collapsed, onToggle, waiting, motion }: {
  groups: NavGroup[]; settings: NavItem | null; collapsed: boolean; onToggle: () => void;
  waiting: ReturnType<typeof useWaitingActions>; motion: boolean;
}) {
  const [folded, setFolded] = useState<Record<string, boolean>>({});
  const nav = useRef<HTMLElement>(null);
  const pill = useRef<HTMLSpanElement>(null);
  const { pathname } = useLocation();

  const moveTo = useCallback((target: HTMLElement | null) => {
    const host = nav.current, node = pill.current;
    if (!host || !node) return;
    if (!target) { node.style.opacity = '0'; return; }
    // Measure against the scrolling nav itself: each group is its own positioned box, so offsetTop
    // would be relative to the group and send the pill back to the first section.
    const top = target.getBoundingClientRect().top - host.getBoundingClientRect().top + host.scrollTop;
    node.style.opacity = '1';
    node.style.transform = `translateY(${top}px)`;
    node.style.height = `${target.offsetHeight}px`;
  }, []);
  const rest = useCallback(() => moveTo(nav.current?.querySelector<HTMLElement>('a[aria-current="page"]') ?? null), [moveTo]);
  useLayoutEffect(rest, [rest, pathname, collapsed, groups, folded]);

  const toggleLabel = collapsed ? 'Expand sidebar' : 'Collapse sidebar';
  return <aside className="hrms-ws-sidebar" aria-label="Workspace">
    <div className="hrms-side-top">
      <TenantHeader />
      <button type="button" className="hrms-side-toggle" onClick={onToggle} aria-label={toggleLabel} title={toggleLabel} aria-pressed={collapsed}>
        <AnimIcon icon={collapsed ? PanelLeftOpenIcon : PanelLeftCloseIcon} size={18} />
      </button>
    </div>

    <nav ref={nav} aria-label="Main navigation" className="hrms-side-nav" onMouseLeave={rest} onBlur={rest}>
      <span ref={pill} className="hrms-side-pill" aria-hidden="true" />
      {groups.map(group => <section key={group.label} className="hrms-side-group" aria-label={group.label}>
        {!group.standalone && <h2><button type="button" className="hrms-side-group-toggle" aria-expanded={!folded[group.label]} onClick={() => setFolded(previous => ({ ...previous, [group.label]: !previous[group.label] }))}>{group.label}<ChevronDown size={14} style={{ transform: folded[group.label] ? "rotate(-90deg)" : undefined }} /></button></h2>}
        {(collapsed || !folded[group.label]) && group.items.map(item => item.comingSoon ? <div key={item.path} className="hrms-side-link hrms-side-coming" data-label={`${item.label} — Coming soon`} aria-disabled="true"><AnimIcon icon={item.icon} size={19} /><span className="hrms-side-label">{item.label}<small>Coming soon</small></span></div> : <NavLink key={item.path} to={item.path} className="hrms-side-link" data-label={item.label}
          onMouseEnter={event => moveTo(event.currentTarget)} onFocus={event => moveTo(event.currentTarget)}>
          <AnimIcon icon={item.icon} size={19} />
          <span className="hrms-side-label">{item.label}</span>
          {item.badge ? <span className="hrms-side-badge" aria-label={`${item.badge} waiting`}>{item.badge > 99 ? '99+' : item.badge}</span> : null}
        </NavLink>)}
      </section>)}
    </nav>

    <div className="hrms-side-bottom">
      {!collapsed && <Link to="/hrms/my-work" className="hrms-side-card" data-anim-trigger>
        <Illustration name="all-clear" animate={motion} className="hrms-side-card-art" />
        <span>
          <strong>{waiting.loading ? 'Checking your work…' : waiting.total > 0 ? `${waiting.total} ${waiting.total === 1 ? 'action' : 'actions'} waiting` : 'You’re all caught up'}</strong>
          <small>{waiting.total > 0 ? 'Open My Tasks to review them' : 'New tasks and approvals appear here'}</small>
        </span>
      </Link>}
      {settings && <NavLink to={settings.path} className="hrms-side-link hrms-side-settings" data-label={settings.label}>
        <AnimIcon icon={settings.icon} size={19} /><span className="hrms-side-label">{settings.label}</span>
      </NavLink>}
    </div>
  </aside>;
}

/* ── Command palette (⌘K) ─────────────────────────────────── */
function CommandPalette({ items, open, onClose }: { items: NavItem[]; open: boolean; onClose: () => void }) {
  const [query, setQuery] = useState('');
  const [index, setIndex] = useState(0);
  const navigate = useNavigate();
  const input = useRef<HTMLInputElement>(null);
  const previous = useRef<HTMLElement | null>(null);
  const results = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return items;
    // Label matches rank above keyword-only matches, and label prefixes above other label matches.
    const rank = (item: NavItem) => {
      const label = item.label.toLowerCase();
      if (label.startsWith(term) || label.split(/\s+/).some(word => word.startsWith(term))) return 0;
      if (label.includes(term)) return 1;
      return (item.keywords ?? '').toLowerCase().includes(term) ? 2 : -1;
    };
    return items.map(item => ({ item, score: rank(item) })).filter(entry => entry.score >= 0)
      .sort((a, b) => a.score - b.score).map(entry => entry.item);
  }, [items, query]);

  useEffect(() => {
    if (!open) return;
    previous.current = document.activeElement as HTMLElement | null;
    input.current?.focus();
    return () => previous.current?.focus();
  }, [open]);

  if (!open) return null;
  const go = (item: NavItem | undefined) => { if (!item) return; onClose(); setQuery(''); setIndex(0); navigate(item.path); };
  const active = Math.min(index, Math.max(results.length - 1, 0));

  return <div className="hrms-palette-backdrop" onPointerDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="hrms-palette" role="dialog" aria-modal="true" aria-label="Jump to a page">
      <label className="hrms-palette-search">
        <AnimIcon icon={SearchIcon} size={18} />
        <span className="sr-only">Search pages</span>
        <input ref={input} value={query} placeholder="Search pages…" role="combobox" aria-expanded="true" aria-controls="hrms-palette-list"
          aria-activedescendant={results[active] ? `hrms-palette-${active}` : undefined}
          onChange={event => { setQuery(event.target.value); setIndex(0); }}
          onKeyDown={event => {
            if (event.key === 'ArrowDown') { event.preventDefault(); setIndex(i => Math.min(i + 1, results.length - 1)); }
            else if (event.key === 'ArrowUp') { event.preventDefault(); setIndex(i => Math.max(i - 1, 0)); }
            else if (event.key === 'Enter') { event.preventDefault(); go(results[active]); }
            else if (event.key === 'Escape') { event.preventDefault(); onClose(); }
          }} />
        <kbd>Esc</kbd>
      </label>
      <ul id="hrms-palette-list" role="listbox" aria-label="Pages">
        {results.map((item, i) => <li key={item.path} id={`hrms-palette-${i}`} role="option" aria-selected={i === active}
          onMouseEnter={() => setIndex(i)} onClick={() => go(item)}>
          <span className="hrms-palette-icon"><AnimIcon icon={item.icon} size={18} play={i === active} /></span>
          <span>{item.label}</span>
          {item.badge ? <span className="hrms-side-badge">{item.badge}</span> : null}
          {i === active && <CornerDownLeft size={15} aria-hidden="true" className="hrms-palette-enter" />}
        </li>)}
        {!results.length && <li className="hrms-palette-empty" role="presentation">No pages match “{query}”.</li>}
      </ul>
      <p className="hrms-palette-hint"><kbd>↑</kbd><kbd>↓</kbd> to move · <kbd>Enter</kbd> to open</p>
    </div>
  </div>;
}

/* ── Top bar popovers ─────────────────────────────────────── */
function Popover({ label, trigger, children, className = '' }: { label: string; trigger: (props: { ref: RefObject<HTMLButtonElement | null>; open: boolean; toggle: () => void }) => ReactNode; children: (close: () => void) => ReactNode; className?: string }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(open, close, root, button);
  return <div ref={root} className={`hrms-pop ${className}`}>
    {trigger({ ref: button, open, toggle: () => setOpen(value => !value) })}
    {open && <div className="hrms-pop-panel" role="dialog" aria-label={label}>{children(close)}</div>}
  </div>;
}

function NotificationBell({ waiting, motion }: { waiting: ReturnType<typeof useWaitingActions>; motion: boolean }) {
  const total = waiting.total;
  return <Popover label="Waiting on you" className="hrms-bell" trigger={({ ref, open, toggle }) =>
    <button ref={ref} type="button" className="hrms-top-icon" aria-expanded={open} aria-haspopup="dialog" onClick={toggle}
      aria-label={total > 0 ? `Notifications: ${total} waiting` : 'Notifications: nothing waiting'}>
      <AnimIcon icon={BellIcon} size={19} every={motion && total > 0 ? 6000 : undefined} />
      {total > 0 && <span className="hrms-bell-dot">{total > 9 ? '9+' : total}</span>}
    </button>}>
    {close => <>
      <header className="hrms-pop-head"><strong>Waiting on you</strong><span>{waiting.loading ? 'Checking…' : `${total} total`}</span></header>
      {total === 0 && !waiting.loading
        ? <div className="hrms-pop-empty"><Illustration name="all-clear" animate={motion} className="hrms-pop-art" /><p>You’re all caught up.</p></div>
        : <ul className="hrms-pop-list">{waiting.sources.map((source: WaitingSource) => <li key={source.key}>
            <Link to={source.path} onClick={close} data-active={source.count > 0}><span>{source.label}</span><b>{source.count}</b></Link>
          </li>)}</ul>}
      <Link to="/hrms/my-work" className="hrms-pop-foot" onClick={close}>Open My Tasks</Link>
    </>}
  </Popover>;
}

function UserMenu({ name, email, roles, initials, canConfigure, onSignOut }: { name: string; email: string; roles: string[]; initials: string; canConfigure: boolean; onSignOut: () => void }) {
  return <Popover label="Account" className="hrms-user-menu" trigger={({ ref, open, toggle }) =>
    <button ref={ref} type="button" className="hrms-user-button" aria-expanded={open} aria-haspopup="dialog" onClick={toggle} aria-label={`Account: ${name}`}>
      <span className="hrms-ws-avatar" aria-hidden="true">{initials}</span>
      <span className="hrms-user-text"><b>{name}</b><small>{roles[0] ?? 'Signed in'}</small></span>
      <ChevronDown size={15} aria-hidden="true" className="hrms-user-chevron" />
    </button>}>
    {close => <>
      <div className="hrms-user-card"><span className="hrms-ws-avatar" aria-hidden="true">{initials}</span><span><b>{name}</b><small>{email}</small></span></div>
      {roles.length > 0 && <ul className="hrms-user-roles" aria-label="Your roles">{roles.map(role => <li key={role}>{role}</li>)}</ul>}
      <nav className="hrms-user-links" aria-label="Account">
        <Link to="/hrms/my-work" onClick={close}><AnimIcon icon={ZapIcon} size={16} />My Tasks</Link>
        {canConfigure && <Link to="/settings" onClick={close}><AnimIcon icon={SettingsIcon} size={16} />Settings</Link>}
        <button type="button" onClick={() => { close(); onSignOut(); }}><LogOut size={16} aria-hidden="true" />Sign out</button>
      </nav>
    </>}
  </Popover>;
}

/* ── Shell ─────────────────────────────────────────────────── */
export function WorkspaceShell() {
  const { user, logout } = useAuth();
  const caps = useHrmsCapabilities();
  const waiting = useWaitingActions();
  const motion = !usePrefersReducedMotion();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [drawerPath, setDrawerPath] = useState(location.pathname);
  const allowed = (capability: string) => caps.data?.capabilities.includes(capability) ?? false;

  // Close the mobile drawer after navigating (state derived during render, no effect needed).
  if (drawerPath !== location.pathname) { setDrawerPath(location.pathname); if (drawerOpen) setDrawerOpen(false); }

  const groups: NavGroup[] = [
    { label: 'Workspace', standalone: true, items: [
      { path: '/hrms/my-work', label: 'My Tasks', icon: ZapIcon, badge: waiting.total, keywords: 'home assigned tasks approvals completion' },
      ...(allowed('employee:read') ? [{ path: '/hrms/employees', label: 'Org Directory', icon: UsersIcon, keywords: 'employees directory people staff' }] : []),
    ] },
    { label: 'Self Service', items: [
      { path: '/hrms/leave', label: 'Leave Requests', icon: CalendarDaysIcon, keywords: 'time off vacation holiday' },
      ...(allowed('wfh:view') ? [{ path: '/hrms/work-from-home', label: 'Work from Home', icon: CalendarDaysIcon, keywords: 'remote work location calendar' }] : []),
      { path: '/hrms/performance', label: 'Performance', icon: TrendingUpIcon, keywords: 'goals reviews feedback cycle' },
      { path: '/hrms/travel', label: 'Travel Request', icon: BriefcaseBusinessIcon, comingSoon: true },
      { path: '/hrms/helpdesk', label: 'Helpdesk', icon: BookTextIcon, comingSoon: true, keywords: 'reimbursements assets workplace documents letters' },
    ] },
    { label: 'Delivery', items: allowed('project:view') ? [
      { path: '/hrms/projects', label: 'Projects', icon: BriefcaseBusinessIcon, keywords: 'customers delivery' },
      { path: '/hrms/allocations', label: 'Allocations', icon: LayoutGridIcon, keywords: 'capacity staffing' },
    ] : [] },
    { label: 'Management', standalone: true, items: [
      ...((allowed('cockpit:view') || allowed('onboarding:view') || allowed('wfh:approve')) ? [{ path: '/hrms/cockpit', label: 'HR Cockpit', icon: SlidersHorizontalIcon, keywords: 'onboarding policies holidays careers publish HR' }] : []),
      { path: '/hrms/assets', label: 'Asset Management', icon: LayoutGridIcon, comingSoon: true },
    ] },
  ].filter(group => group.items.length);
  const settings: NavItem | null = allowed('platform:configure') ? { path: '/settings', label: 'Settings', icon: SettingsIcon, keywords: 'configuration roles forms' } : null;
  const paletteItems = [...groups.flatMap(group => group.items).filter(item => !item.comingSoon), { path: '/hrms/content', label: 'Company resources', icon: BookTextIcon, keywords: 'policies learning holidays careers published' }, ...(settings ? [settings] : [])];

  const current = groups.flatMap(group => group.items.map(item => ({ ...item, group: group.standalone ? item.label : group.label }))).find(item => location.pathname.startsWith(item.path))
    ?? (location.pathname.startsWith('/settings') && settings ? { ...settings, group: 'Configuration' } : location.pathname.startsWith('/hrms/content') ? { ...paletteItems.find(i => i.path === '/hrms/content')!, group: 'Resources' } : null);
  const roles = caps.data?.roles.map(roleName) ?? [];
  const initials = (user?.fullName ?? '').split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0]?.toUpperCase()).join('') || '·';

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setPaletteOpen(open => !open); }
      if (event.key === 'Escape') setDrawerOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const toggleCollapsed = () => setCollapsed(value => {
    const next = !value;
    try { localStorage.setItem(COLLAPSE_KEY, next ? '1' : '0'); } catch { /* preference only */ }
    return next;
  });
  const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);

  return <div className={`hrms-brand hrms-ws-shell${motion ? ' hrms-ws--motion' : ''}`} data-collapsed={collapsed} data-drawer={drawerOpen}>
    <Sidebar groups={groups} settings={settings} collapsed={collapsed} onToggle={toggleCollapsed} waiting={waiting} motion={motion} />
    {drawerOpen && <div className="hrms-side-scrim" onClick={() => setDrawerOpen(false)} aria-hidden="true" />}

    <div className="hrms-ws-main">
      <header className="hrms-ws-topbar">
        <button type="button" className="hrms-top-icon hrms-top-menu" onClick={() => setDrawerOpen(open => !open)} aria-label={drawerOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={drawerOpen}>
          <AnimIcon icon={drawerOpen ? XIcon : MenuIcon} size={19} />
        </button>
        <div className="hrms-ws-crumbs">
          {current && <span className="hrms-crumb-icon" data-anim-trigger><AnimIcon icon={current.icon} size={17} every={motion ? 9000 : undefined} /></span>}
          <p>{current ? <>{current.group.toLowerCase() !== current.label.toLowerCase() && <><span>{current.group}</span><i aria-hidden="true">/</i></>}<strong>{current.label}</strong></> : <strong>Workspace</strong>}</p>
        </div>
        <button type="button" className="hrms-top-search" onClick={() => setPaletteOpen(true)} aria-label="Search or jump to a page" aria-keyshortcuts="Meta+K Control+K">
          <AnimIcon icon={SearchIcon} size={16} /><span>Search or jump to…</span><kbd>{isMac ? '⌘' : 'Ctrl'} K</kbd>
        </button>
        <div className="hrms-top-actions">
          <NotificationBell waiting={waiting} motion={motion} />
          <UserMenu name={user?.fullName ?? 'Signed in'} email={user?.email ?? ''} roles={roles} initials={initials} canConfigure={Boolean(settings)} onSignOut={() => void logout()} />
        </div>
      </header>
      <div className="hrms-ws-content"><Outlet /></div>
    </div>

    <CommandPalette items={paletteItems} open={paletteOpen} onClose={() => setPaletteOpen(false)} />
  </div>;
}
