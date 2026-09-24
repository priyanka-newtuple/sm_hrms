import { useState, type CSSProperties, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { LogOut, ChevronRight, ChevronDown, Gift, Search } from 'lucide-react';
import { useAuth } from '../core/auth';
import { usePermissions } from '../core/hooks/usePermissions';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from '../components/ui/dropdown-menu';
import { useAgent, AgentSidebar, AgentToggle } from '../core/agent';
import { useSkin } from '@/skins';
import type { NavItem } from '@/skins';
import { useFeatureFlags, type FeatureFlags } from '../core/hooks/useFeatureFlags';
import { NotificationBell } from '../core/components';
import { ThemeModeToggle } from '../core/components/ThemeModeToggle';
import GlobalEntityFilterSelector from '../core/components/GlobalEntityFilterSelector';
import {
  GlobalEntityFilterProvider,
  useGlobalEntityFilter,
} from '../core/contexts/GlobalEntityFilterContext';
import { OrgSwitcher } from '../core/components/OrgSwitcher';
import { useWorkflows } from '../shared/hooks/useWorkflows';
import { useBreadcrumbs } from '../shared/hooks/useBreadcrumbs';
import { useAppLabels, type AppLabels, useNavLayout } from '../shared/hooks';
import Breadcrumbs from '../core/components/Breadcrumbs';
import { CommandPalette } from '../core/components/CommandPalette';
import { useCommandPaletteStore } from '../core/stores/commandPaletteStore';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarProvider,
  SidebarSeparator,
  SidebarTrigger,
} from '../components/ui/sidebar';

interface AppLayoutProps {
  children: ReactNode;
}

/**
 * Tints the main nav rail with a hint of the configured top-bar color.
 * Scoped to this <Sidebar> only so the settings page sidebar keeps neutral defaults.
 */
const SIDEBAR_TINT_STYLE: CSSProperties = {
  '--sidebar': 'color-mix(in srgb, var(--header-background) 6%, var(--sidebar-base))',
  '--sidebar-accent': 'color-mix(in srgb, var(--header-background) 12%, var(--sidebar-accent-base))',
  '--sidebar-border': 'color-mix(in srgb, var(--header-background) 16%, var(--sidebar-border-base))',
} as CSSProperties;

/**
 * Recolors the OrgSwitcher (built for the `<Sidebar>`'s light chrome) to read
 * against the configured top-bar color, for the topbar nav layout where no
 * `<Sidebar>` wrapper exists to supply these tokens.
 */
const TOPBAR_ORG_SWITCHER_STYLE: CSSProperties = {
  '--sidebar-foreground': 'var(--header-foreground)',
  '--sidebar-accent': 'color-mix(in srgb, var(--header-foreground) 14%, transparent)',
  '--sidebar-accent-foreground': 'var(--header-foreground)',
  '--sidebar-ring': 'var(--header-foreground)',
} as CSSProperties;

function getUserInitials(fullName: string | undefined): string {
  if (!fullName) return 'U';
  const names = fullName.split(' ');
  if (names.length >= 2) return `${names[0][0]}${names[names.length - 1][0]}`.toUpperCase();
  return names[0][0].toUpperCase();
}

function getRoleDisplay(role: string): string {
  const roleMap: Record<string, string> = {
    admin: 'Admin',
    recruiter: 'Recruiter',
    hiring_manager: 'Hiring Manager',
    viewer: 'Viewer',
  };
  return roleMap[role] || role;
}

/** Filters skin nav items by the organization's feature flags (Settings → Display). */
function applyFlagFilters(items: NavItem[], flags: FeatureFlags): NavItem[] {
  return items.filter((item) => {
    if (item.path === '/dashboard' && flags.hideDashboard) return false;
    if (item.path === '/records' && flags.hideRecords) return false;
    if (item.path === '/changelogs' && flags.hideWhatsNew) return false;
    return true;
  });
}

/** Account dropdown body (profile header + What's New + Sign out), shared by both nav layouts. */
function UserMenuContent({ side = 'top', align = 'start' }: {
  side?: 'top' | 'bottom';
  align?: 'start' | 'end';
}) {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const featureFlags = useFeatureFlags();

  return (
    <DropdownMenuContent side={side} align={align} className="w-64 p-0">
      <div className="flex items-center gap-2.5 px-3 py-2.5">
        {user?.avatarUrl ? (
          <img
            src={user.avatarUrl}
            alt={user.fullName}
            className="h-9 w-9 rounded-lg object-cover"
          />
        ) : (
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <span className="text-xs font-semibold">{getUserInitials(user?.fullName)}</span>
          </div>
        )}
        <div className="flex-1 min-w-0">
          <p className="truncate text-sm font-medium leading-tight text-popover-foreground">
            {user?.fullName}
          </p>
          <p className="truncate text-[11px] text-muted-foreground">{user?.email}</p>
        </div>
        <span className="rounded-md bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold text-primary">
          {getRoleDisplay(user?.role || '')}
        </span>
      </div>

      <DropdownMenuSeparator />

      {/* Opt-in per org. The trailing separator is inside the guard so hiding
          the switch doesn't leave two rules stacked on each other.
          Plain buttons, not DropdownMenuItems — picking a mode should recolor
          the app in place, not dismiss the menu. */}
      {featureFlags.darkModeEnabled && (
        <>
          <div className="px-2 py-2" onClick={(e) => e.stopPropagation()}>
            <ThemeModeToggle />
          </div>

          <DropdownMenuSeparator />
        </>
      )}

      <div className="p-1">
        {!featureFlags.hideWhatsNew && (
          <DropdownMenuItem onClick={() => navigate('/changelogs')}>
            <Gift className="size-4 text-muted-foreground" />
            What's New
          </DropdownMenuItem>
        )}
        <DropdownMenuItem variant="destructive" onClick={() => { void logout(); }}>
          <LogOut className="size-4" />
          Sign out
        </DropdownMenuItem>
      </div>
    </DropdownMenuContent>
  );
}

/** Horizontal nav button styling for the top-bar layout; inherits the header foreground. */
function topNavButtonClass(active: boolean): string {
  return cn(
    'flex h-9 shrink-0 cursor-pointer items-center gap-2 rounded-lg px-3 text-sm font-medium whitespace-nowrap transition-colors [&_svg]:size-4',
    active
      ? 'bg-[color-mix(in_srgb,var(--header-foreground)_14%,transparent)] text-[var(--header-foreground)]'
      : 'opacity-70 hover:opacity-100 hover:bg-[color-mix(in_srgb,var(--header-foreground)_8%,transparent)]',
  );
}

/** "Quick actions" button that opens the ⌘K command palette. Two skins: a
 *  full-width bordered field in the sidebar, a compact pill in the top bar. */
function SearchTrigger({ variant }: { variant: 'sidebar' | 'topbar' }) {
  const setOpen = useCommandPaletteStore((s) => s.setOpen);

  if (variant === 'sidebar') {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open quick actions"
        className="mt-1 flex h-9 w-full items-center gap-2.5 rounded-lg bg-sidebar-accent/50 px-2.5 text-sm text-sidebar-foreground/65 transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:bg-transparent group-data-[collapsible=icon]:px-0"
      >
        <Search className="size-4 shrink-0 [stroke-width:1.75]" />
        <span className="flex-1 text-left group-data-[collapsible=icon]:hidden">Quick actions</span>
        <kbd className="pointer-events-none font-mono text-[10px] leading-none tracking-widest text-sidebar-foreground/40 group-data-[collapsible=icon]:hidden">
          ⌘K
        </kbd>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={() => setOpen(true)}
      aria-label="Open quick actions"
      className="flex h-9 shrink-0 items-center gap-2 rounded-lg border border-[color-mix(in_srgb,var(--header-foreground)_20%,transparent)] px-3 text-sm opacity-80 transition-colors hover:bg-[color-mix(in_srgb,var(--header-foreground)_8%,transparent)] hover:opacity-100 [&_svg]:size-4"
    >
      <Search />
      <span className="hidden lg:inline">Quick actions</span>
      <kbd className="hidden rounded border border-[color-mix(in_srgb,var(--header-foreground)_20%,transparent)] px-1.5 py-0.5 font-mono text-[10px] leading-none lg:inline">
        ⌘K
      </kbd>
    </button>
  );
}

function AppLayoutFrame({ children }: AppLayoutProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const breadcrumbs = useBreadcrumbs();
  const { user } = useAuth();
  const { hasPermission } = usePermissions();
  const { isOpen: isAgentOpen, sidebarWidth } = useAgent();
  const { workflows } = useWorkflows();
  const { skin } = useSkin();
  const featureFlags = useFeatureFlags();
  const { settings: globalEntityFilterSettings } = useGlobalEntityFilter();
  const globalFilterPlacement = globalEntityFilterSettings.placement;
  // A skin may fully own the sidebar via the 'sidebar' slot; otherwise the
  // platform renders its default skin-driven sidebar below.
  const SkinSidebar = skin.components?.sidebar;
  // A skin may likewise own the top bar via the 'topbar' slot, replacing the
  // platform's default two-row header in the 'topbar' nav layout.
  const SkinTopbar = skin.components?.topbar;
  const appLabels = useAppLabels();

  const [isPipelineSubmenuOpen, setIsPipelineSubmenuOpen] = useState(
    location.pathname.startsWith('/pipeline') || location.pathname.startsWith('/workflows'),
  );

  // Overlay per-org label overrides on the built-in nav labels, keyed by route slug.
  const allNavItems = applyFlagFilters(skin.navigation, featureFlags).map((item) => {
    const key = item.path.replace(/^\//, '') as keyof AppLabels;
    return key in appLabels ? { ...item, label: appLabels[key] } : item;
  });

  const topNavItems = allNavItems.filter((item) => item.position !== 'bottom');

  const bottomNavItems = allNavItems
    .filter((item) => item.position === 'bottom')
    .filter((item) => item.path !== '/settings' || hasPermission('settings:access'));

  // Every reachable nav destination, flattened for the ⌘K command palette.
  const paletteNavItems = [...topNavItems, ...bottomNavItems];

  const isPathActive = (path: string) =>
    path === '/'
      ? location.pathname === '/'
      : location.pathname === path || location.pathname.startsWith(path + '/');

  const isPipelineActive =
    location.pathname.startsWith('/pipeline') || location.pathname.startsWith('/workflows');

  const navLayout = useNavLayout();

  if (navLayout === 'topbar') {
    return (
      // SidebarProvider stays for context consumers (OrgSwitcher); no Sidebar is rendered.
      <SidebarProvider>
        <SidebarInset
          style={{ '--agent-sidebar-width': `${sidebarWidth}px` } as CSSProperties}
          className={cn(
            'bg-[var(--content-background)] min-w-0 transition-[margin] duration-300 ease-out',
            isAgentOpen && 'sm:mr-[var(--agent-sidebar-width)]',
          )}
        >
          {/* A skin that owns the 'topbar' slot renders its own header chrome. */}
          {SkinTopbar && <SkinTopbar />}

          {/* Top bar — a skin may opt out entirely via hideTopBar when its own sidebar already carries navigation/branding. */}
          {!SkinTopbar && !skin.hideTopBar && (
            <>
              {/* Top bar, layer 1: org switcher + actions */}
              <header className="sticky top-0 z-40 flex h-[var(--header-height)] items-center gap-2 border-b border-[color-mix(in_srgb,var(--header-foreground)_12%,transparent)] bg-[var(--header-background)] px-4 text-[var(--header-foreground)]">
                <div className="w-56 shrink-0 text-sidebar-foreground" style={TOPBAR_ORG_SWITCHER_STYLE}>
                  <OrgSwitcher dropdownSide="bottom" />
                </div>
                {skin.branding.subtitle && (
                  <span className="hidden shrink-0 truncate text-[11px] font-medium uppercase tracking-wider opacity-45 lg:inline">
                    {skin.branding.subtitle}
                  </span>
                )}

                {globalFilterPlacement === 'left' && <GlobalEntityFilterSelector />}

                <div className="flex-1" />

                <SearchTrigger variant="topbar" />

                {/* Agent Mode — sits directly before What's New / Settings in the top bar. */}
                {!featureFlags.hideAgent && hasPermission('agent:read') && <AgentToggle />}

                {bottomNavItems.map((item) => (
                  <button
                    key={item.path}
                    type="button"
                    onClick={() => navigate(item.path)}
                    className={topNavButtonClass(isPathActive(item.path))}
                  >
                    <item.icon />
                    {item.label}
                  </button>
                ))}

                {globalFilterPlacement === 'right' && <GlobalEntityFilterSelector />}
                <NotificationBell />

                {/* User menu */}
                <DropdownMenu>
                  <DropdownMenuTrigger
                    render={<button type="button" aria-label="Account" className="shrink-0 cursor-pointer rounded-full" />}
                  >
                    {user?.avatarUrl ? (
                      <img src={user.avatarUrl} alt={user.fullName} className="size-8 rounded-full object-cover" />
                    ) : (
                      <span className="flex size-8 items-center justify-center rounded-full bg-primary text-xs font-medium text-primary-foreground">
                        {getUserInitials(user?.fullName)}
                      </span>
                    )}
                  </DropdownMenuTrigger>
                  <UserMenuContent side="bottom" align="end" />
                </DropdownMenu>
              </header>

              {/* Top bar, layer 2: horizontal nav */}
              <nav className="sticky top-[var(--header-height)] z-30 flex h-11 items-center gap-1 overflow-x-auto border-b border-[color-mix(in_srgb,var(--header-foreground)_12%,transparent)] bg-[color-mix(in_srgb,var(--header-background)_92%,black)] px-4 text-[var(--header-foreground)]">
                {topNavItems.map((item) => {
                  const isActive = item.showPipelineSubmenu ? isPipelineActive : isPathActive(item.path);

                  if (!item.showPipelineSubmenu) {
                    return (
                      <button
                        key={item.path}
                        type="button"
                        onClick={() => navigate(item.path)}
                        className={topNavButtonClass(isActive)}
                      >
                        <item.icon />
                        {item.label}
                      </button>
                    );
                  }

                  // Pipeline item: workflows move into a dropdown instead of a sub-menu.
                  return (
                    <DropdownMenu key={item.path}>
                      <DropdownMenuTrigger
                        render={<button type="button" className={topNavButtonClass(isActive)} />}
                      >
                        <item.icon />
                        {item.label}
                        <ChevronDown className="!size-3.5 opacity-60" />
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="start" className="w-56">
                        <DropdownMenuItem onClick={() => navigate(item.path)}>
                          <item.icon className="size-4 text-muted-foreground" />
                          {item.label}
                        </DropdownMenuItem>
                        {workflows.length > 0 && <DropdownMenuSeparator />}
                        {workflows.map((wf) => (
                          <DropdownMenuItem key={wf.slug} onClick={() => navigate(`/pipeline/${wf.id}`)}>
                            <span
                              aria-label={wf.isActive ? 'Active' : 'Draft'}
                              className={cn(
                                'size-2 rounded-full flex-shrink-0',
                                wf.isActive ? 'bg-emerald-500' : 'bg-amber-500',
                              )}
                            />
                            {wf.label}
                          </DropdownMenuItem>
                        ))}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  );
                })}
              </nav>
            </>
          )}

          {/* Page content */}
          <main
            className={cn(
              'min-w-0',
              // A skin-provided topbar (see TopbarSlotProps) is a single
              // --header-height row, not the platform's own two-row chrome.
              SkinTopbar
                ? 'min-h-[calc(100svh-var(--header-height))]'
                : skin.hideTopBar
                  ? 'min-h-svh'
                  : 'min-h-[calc(100svh-var(--header-height)-2.75rem)]',
            )}
          >
            <div className="mx-auto w-full max-w-[var(--content-max-width)] min-w-0 p-4 lg:px-12 lg:py-8">
              {children}
            </div>
          </main>

          {!featureFlags.hideAgent && <AgentSidebar />}
          <CommandPalette navItems={paletteNavItems} />
        </SidebarInset>
      </SidebarProvider>
    );
  }

  return (
    <SidebarProvider style={{ '--sidebar-width': SkinSidebar ? '17.5rem' : '14.5rem' } as CSSProperties}>
      {SkinSidebar ? (
        <Sidebar collapsible="none" className="border-r-transparent shadow-lg" style={{ ...SIDEBAR_TINT_STYLE, '--sidebar-width': '17.5rem' } as CSSProperties}>
          <SkinSidebar />
        </Sidebar>
      ) : (
        <Sidebar collapsible="icon" className="border-r-transparent" style={SIDEBAR_TINT_STYLE}>

          {/* Org switcher + optional product subtitle */}
          <SidebarHeader className="p-2">
            <OrgSwitcher />
            {skin.branding.subtitle && (
              <p className="px-2 pt-0.5 pb-1 text-[11px] font-medium uppercase tracking-wider text-sidebar-foreground/55 group-data-[collapsible=icon]:hidden">
                {skin.branding.subtitle}
              </p>
            )}
            <SearchTrigger variant="sidebar" />
          </SidebarHeader>

          {/* Main nav */}
          <SidebarContent className="px-2 py-3">
            <SidebarGroup className="p-0">
              <SidebarGroupContent>
                <SidebarMenu className="gap-1">
                  {topNavItems.map((item) => {
                    // The pipeline row is a section header: when its section is active it gets
                    // quiet emphasis (colored icon + medium weight), never the filled pill — the
                    // active workflow leaf below carries the single highlight. Regular items fill.
                    const isPipelineHeader = !!item.showPipelineSubmenu;
                    const isActive = isPipelineHeader ? isPipelineActive : isPathActive(item.path);
                    const buttonActiveClass = !isActive
                      ? 'text-sidebar-foreground/75 hover:text-sidebar-foreground'
                      : isPipelineHeader
                        ? 'font-medium text-sidebar-foreground [&_svg]:!text-[var(--sidebar-primary)]'
                        : '!bg-[var(--sidebar-active)] font-medium text-sidebar-foreground';

                    return (
                      <SidebarMenuItem key={item.path}>
                        <SidebarMenuButton
                          onClick={() => {
                            navigate(item.path);
                            if (item.showPipelineSubmenu) setIsPipelineSubmenuOpen(true);
                          }}
                          isActive={isPipelineHeader ? false : isActive}
                          tooltip={item.label}
                          className={cn('h-9 rounded-lg [&_svg]:[stroke-width:1.75]', buttonActiveClass)}
                        >
                          <item.icon />
                          <span>{item.label}</span>
                          {item.showPipelineSubmenu && (
                            <ChevronRight
                              onClick={(e) => {
                                e.stopPropagation();
                                setIsPipelineSubmenuOpen((open) => !open);
                              }}
                              className={cn(
                                'ml-auto transition-transform group-data-[collapsible=icon]:hidden',
                                isPipelineSubmenuOpen && 'rotate-90',
                              )}
                            />
                          )}
                        </SidebarMenuButton>

                        {/* Dynamic pipeline list — flat workflow chips, hidden when the
                            rail collapses to icons. Active workflow gets a soft brand pill;
                            the status dot is filled for a live workflow, a hollow ring for a
                            draft (so active/draft reads without relying on color alone). */}
                        {item.showPipelineSubmenu && isPipelineSubmenuOpen && (
                          <div className="mt-0.5 ml-3 flex flex-col gap-0.5 group-data-[collapsible=icon]:hidden">
                            {workflows.length === 0 ? (
                              <span className="px-2.5 py-1 text-xs text-sidebar-foreground/45">
                                No workflows
                              </span>
                            ) : (
                              workflows.map((wf) => {
                                const path = `/pipeline/${wf.id}`;
                                const active = isPathActive(path);
                                return (
                                  <button
                                    key={wf.slug}
                                    type="button"
                                    onClick={() => navigate(path)}
                                    aria-current={active ? 'page' : undefined}
                                    className={cn(
                                      'flex h-8 items-center gap-2.5 rounded-lg px-2.5 text-left text-[13px] transition-colors',
                                      active
                                        ? 'bg-[var(--sidebar-active)] font-medium text-sidebar-foreground'
                                        : 'text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground',
                                    )}
                                  >
                                    <span
                                      aria-label={wf.isActive ? 'Active' : 'Draft'}
                                      className={cn(
                                        'size-1.5 shrink-0 rounded-full',
                                        wf.isActive
                                          ? 'bg-emerald-500'
                                          : 'border border-amber-500 bg-transparent',
                                      )}
                                    />
                                    <span className="truncate">{wf.label}</span>
                                  </button>
                                );
                              })
                            )}
                          </div>
                        )}
                      </SidebarMenuItem>
                    );
                  })}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          </SidebarContent>

          {/* Footer: bottom nav items + user menu */}
          <SidebarFooter className="p-2">
            {bottomNavItems.length > 0 && <SidebarSeparator className="mb-1" />}
            {/* Agent Mode CTA — sits just before What's New in the footer. */}
            {!featureFlags.hideAgent && hasPermission('agent:read') && (
              <div className="mb-1">
                <AgentToggle variant="sidebar" />
              </div>
            )}
            {bottomNavItems.length > 0 && (
              <>
                <SidebarMenu className="gap-1">
                  {bottomNavItems.map((item) => (
                    <SidebarMenuItem key={item.path}>
                      <SidebarMenuButton
                        onClick={() => navigate(item.path)}
                        isActive={isPathActive(item.path)}
                        tooltip={item.label}
                        className={cn(
                          'h-9 rounded-lg [&_svg]:[stroke-width:1.75]',
                          isPathActive(item.path)
                            ? '!bg-[var(--sidebar-active)] font-medium text-sidebar-foreground'
                            : 'text-sidebar-foreground/75 hover:text-sidebar-foreground',
                        )}
                      >
                        <item.icon />
                        <span>{item.label}</span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              </>
            )}

            {/* User menu */}
            <DropdownMenu>
              <SidebarMenu>
                <SidebarMenuItem>
                  <DropdownMenuTrigger render={
                    <SidebarMenuButton size="lg" tooltip={user?.fullName || 'Account'} />
                  }>
                    {user?.avatarUrl ? (
                      <img
                        src={user.avatarUrl}
                        alt={user.fullName}
                        className="w-6 h-6 rounded-lg object-cover flex-shrink-0"
                      />
                    ) : (
                      <div className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-lg bg-primary">
                        <span className="text-[10px] font-medium text-primary-foreground">
                          {getUserInitials(user?.fullName)}
                        </span>
                      </div>
                    )}
                    <span className="flex flex-col min-w-0">
                      <span className="text-sm font-medium truncate">{user?.fullName}</span>
                      <span className="text-xs text-sidebar-foreground/60 truncate">
                        {getRoleDisplay(user?.role || '')}
                      </span>
                    </span>
                  </DropdownMenuTrigger>
                </SidebarMenuItem>
              </SidebarMenu>

              <UserMenuContent />
            </DropdownMenu>
          </SidebarFooter>

        </Sidebar>
      )}

      {/* Main content */}
      <SidebarInset
        style={{ '--agent-sidebar-width': `${sidebarWidth}px` } as CSSProperties}
        className={cn(
          'bg-[var(--content-background)] min-w-0 transition-[margin] duration-300 ease-out',
          isAgentOpen && 'sm:mr-[var(--agent-sidebar-width)]',
        )}
      >
        {/* Top bar — a skin may opt out entirely via hideTopBar when its own sidebar already carries navigation/branding. */}
        {!skin.hideTopBar && (
          <header className="sticky top-0 z-40 flex h-[var(--header-height)] items-center gap-3 border-b border-border/60 bg-[var(--header-background)] px-4 text-[var(--header-foreground)]">
            <SidebarTrigger size="lg" />
            <Breadcrumbs items={breadcrumbs} />
            {globalFilterPlacement === 'left' && <GlobalEntityFilterSelector />}
            <div className="flex-1" />
            {globalFilterPlacement === 'right' && <GlobalEntityFilterSelector />}
            {/* Agent Mode moved to the sidebar footer CTA (see SidebarFooter). */}
            <NotificationBell />
          </header>
        )}

        {/* Page content */}
        <main className={cn('min-w-0', skin.hideTopBar ? 'min-h-svh' : 'min-h-[calc(100svh-var(--header-height))]')}>
          <div className="mx-auto w-full max-w-[var(--content-max-width)] min-w-0 p-4 lg:px-12 lg:py-8">
            {children}
          </div>
        </main>

        {!featureFlags.hideAgent && <AgentSidebar />}
        <CommandPalette navItems={paletteNavItems} />
      </SidebarInset>
    </SidebarProvider>
  );
}

export default function AppLayout({ children }: AppLayoutProps) {
  return (
    <GlobalEntityFilterProvider>
      <AppLayoutFrame>{children}</AppLayoutFrame>
    </GlobalEntityFilterProvider>
  );
}
