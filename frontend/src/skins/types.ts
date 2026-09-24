/**
 * Skin Manifest Type Definitions
 *
 * Defines the shape of a skin configuration. A skin is the single source of
 * truth for branding, navigation, entity model, board behaviour, and view
 * layout for one deployment of the platform (ATS, CRM, PMO, …).
 *
 * All fields added here must remain generic — no domain-specific field names.
 * Any skin (not just the default) must be able to supply meaningful values.
 */

import type React from 'react';
import type { LucideIcon } from 'lucide-react';
import type { OrgTheme } from '../core/theme';
import type { SkinComponents } from '../core/componentRegistry';
import type { WorkflowEntityState } from '../core/services/api';
import type { UserPublic } from '../core/auth/types';

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

/** A single item in the sidebar navigation */
export interface NavItem {
  /** Route path (e.g. "/dashboard") */
  path: string;
  /** Human-readable label */
  label: string;
  /** Lucide icon component */
  icon: LucideIcon;
  /** Where to render this item — top of the nav list or pinned to the bottom */
  position?: 'top' | 'bottom';
  /**
   * When true, this nav item renders an expandable sub-list of the platform's
   * active pipeline / workflow instances below it.
   * Only one item in a skin's navigation should set this to true.
   */
  showPipelineSubmenu?: boolean;
  /**
   * When set, clicking this nav item opens the given base URL in a new tab.
   * The layout injects the current session tokens into the URL hash so the
   * target app can authenticate without a separate login.
   * Format: base URL without hash (e.g. "https://opstats.example.com/opstats/wizard")
   */
  externalUrl?: string;
}

// ---------------------------------------------------------------------------
// Branding
// ---------------------------------------------------------------------------

/** Product identity and legal copy */
export interface BrandingConfig {
  /** Full product name shown on the login page and in the browser tab */
  name: string;
  /** Abbreviated name used in constrained spaces (e.g. mobile header) */
  shortName: string;
  /** One or two letter monogram rendered when no logo image is set */
  logoText: string;
  /** URL of a logo image; when set it replaces the logoText monogram */
  logoUrl?: string;
  /** Primary brand color key (used by the theme system) */
  primaryColor: string;
  /** Copyright holder shown in the login footer */
  copyrightOwner: string;
  /** Release date shown on the login page */
  releaseDate?: string;
  /**
   * Optional product subtitle shown below the brand name in the sidebar
   * (e.g. "ResolverIQ" under "Cititrends")
   */
  subtitle?: string;
}

// ---------------------------------------------------------------------------
// Entity types
// ---------------------------------------------------------------------------

/** Describes one entity type managed by the platform */
export interface EntityTypeConfig {
  /** Entity type string used in API calls (e.g. "ATS.Application") */
  entityType: string;
  /** JSON schema name for creating entities of this type */
  schemaName: string;
  /** Default schema version */
  schemaVersion: number;
  /** Name of the state machine that governs this entity type (if stateful) */
  machineName?: string;
  /** State machine version to use (defaults to 1) */
  machineVersion?: number;
  /** Singular human-readable label (e.g. "Application") */
  label: string;
  /** Plural human-readable label (e.g. "Applications") */
  labelPlural: string;
}

// ---------------------------------------------------------------------------
// Board — filter bar
// ---------------------------------------------------------------------------

/** Input type for a filter bar item */
export type FilterBarItemType = 'search' | 'select' | 'daterange' | 'assignee' | 'multiselect';

/**
 * A single control in the board filter bar.
 *
 * The `key` is used as the query-param name and local state key, so it must
 * be unique within a skin's filterBar array.
 */
export interface FilterBarItem {
  /** Unique key for this filter — used as the query param name and entity.data field */
  key: string;
  /** Human-readable label rendered above or inside the control */
  label: string;
  /** Which kind of input to render */
  type: FilterBarItemType;
  /**
   * Inline options list for 'select'/'multiselect' filters.
   * Prefer `staticListKey` when the options are already declared in `skin.staticLists`.
   */
  staticOptions?: string[];
  /** Optional display labels parallel to `staticOptions`. */
  staticOptionLabels?: string[];
  /**
   * Name of a `skin.staticLists` entry to use as the options list for a 'select' filter.
   * Takes precedence over `staticOptions` when both are set.
   * @example 'departments' → skin.staticLists.departments
   */
  staticListKey?: string;
  /** Placeholder text for 'search' type inputs */
  placeholder?: string;
}

// ---------------------------------------------------------------------------
// Board — action buttons
// ---------------------------------------------------------------------------

/** Visual weight/style of an action button */
export type ActionButtonStyle = 'primary' | 'secondary' | 'warning' | 'danger';

/**
 * An action button rendered in the entity detail view header.
 *
 * The button is only shown when `triggerName` is a valid transition from the
 * entity's current state. If `modalSlot` is set, clicking the button opens
 * the named component slot as a modal before the transition executes.
 */
export interface ActionButtonConfig {
  /** Label shown on the button */
  label: string;
  /** State machine transition trigger to execute on confirmation */
  triggerName: string;
  /** Visual style applied to the button */
  style: ActionButtonStyle;
  /** Optional Lucide icon displayed alongside the label */
  icon?: LucideIcon;
  /**
   * Name of the component slot to open as a pre-transition modal.
   * When omitted the transition fires immediately on click.
   * (Resolved against the ComponentRegistry in the skin — see STAT-211.)
   */
  modalSlot?: string;
}

// ---------------------------------------------------------------------------
// Board / Pipeline configuration
// ---------------------------------------------------------------------------

/** A pipeline stage used for rendering and fallback purposes */
export interface StageConfig {
  /** State name from the state machine definition */
  state: string;
  /** Human-readable display label */
  label: string;
  /**
   * CSS color value for this stage (hex / hsl / oklch).
   * Used to tint column headers and badges in the board.
   * Must be a raw CSS color — NOT a Tailwind class.
   */
  color: string;
}

/** Full board/pipeline configuration */
export interface BoardConfig {
  /** Entity type to display on the board */
  entityType: string;
  /** State machine name to fetch live stages from */
  machineName: string;
  /** Stages to render when the state machine cannot be fetched from the API */
  fallbackStages: StageConfig[];
  /** States that are excluded from the board columns (shown in list/table views only) */
  terminalStates: string[];
  /**
   * Per-state CSS color values (hex / hsl / oklch).
   * Used for column header dots, tinted backgrounds, and badges.
   * Must be raw CSS colors — NOT Tailwind classes.
   *
   * @example { APPLIED: '#9ca3af', SCREENING: '#60a5fa' }
   */
  stateColors: Record<string, string>;
  /**
   * Per-state display label overrides (state name -> label).
   * Falls back to the auto-derived title-cased label when a state has no
   * override here. Use when the workflow's raw state names don't title-case
   * cleanly (e.g. "INPROGRESS" -> "In Progress" needs an explicit override).
   *
   * @example { INPROGRESS: 'In Progress' }
   */
  stateLabels?: Record<string, string>;

  // --- Display customisation -------------------------------------------------

  /** Override the board page heading (defaults to the workflow / entity type name) */
  pageTitle?: string;
  /**
   * Override the page heading's className entirely (replaces, not merges,
   * the default `"truncate text-xl font-semibold text-gray-900"`). Use when
   * a skin's own design system specifies a different title treatment than
   * the platform default.
   */
  titleClassName?: string;
  /**
   * Rename the view toggle tabs.
   * Defaults: { kanban: 'Kanban', list: 'List' }
   */
  viewLabels?: { kanban?: string; list?: string };
  /** Show an "Export CSV" button in the board header */
  showExportCsv?: boolean;
  /**
   * Visual style of the export control.
   *   'dropdown' (default) — multi-format button that opens a field-picker slide-over.
   *   'csv' — single-click plain-text button that exports the default field
   *   selection straight to CSV, no picker.
   */
  exportStyle?: 'dropdown' | 'csv';
  /** Show the "Add {Entity}" button in the board header. Defaults to true. */
  showAddEntity?: boolean;
  /**
   * Hard-disables the Jira-style assignee avatar-filter (click an avatar to
   * toggle, "+N" opens a full checkbox picker) on Board/Table/Calendar,
   * regardless of the org's own Settings → Display toggle. Defaults to true
   * (allowed); set to false for a skin whose entities don't have a
   * meaningful assignee concept, or that ships its own assignee filtering.
   * Even when true, the filter is only actually shown for orgs that have
   * opted in via `featureFlags.hideAssigneeFilter: false` — see useFeatureFlags.
   */
  showAssigneeFilter?: boolean;
  /** Hide INITIAL / TERMINAL badges on kanban column headers */
  hideTerminalBadge?: boolean;
  /** Hide the transition metadata row ("↳ Out X → In Y") on column headers */
  hideTransitionMeta?: boolean;
  /** Hide the "N columns · N entities" meta row above the kanban columns. */
  hideBoardMeta?: boolean;
  /**
   * 'header' (default): Add button and Export control render in the page
   * header, view tabs and filters render in a row below.
   * 'unified': view tabs move into the page header (top-right, beside the
   * title) and the Export control moves down beside the filter bar, so
   * search/filters/export share a single row below the title.
   */
  toolbarLayout?: 'header' | 'unified';
  /**
   * Custom empty-lane message.
   * Defaults to "No <state> entities yet."
   */
  emptyLaneText?: string;
  /**
   * Background color for kanban columns (any valid CSS color).
   * When omitted the column uses the default per-state tinted background
   * derived from `stateColors`.
   */
  columnBackground?: string;
  /**
   * Override the kanban column wrapper's className entirely (replaces the
   * platform default). Use when a skin's own design system specifies a
   * different column treatment (border, radius, shadow, padding) than the
   * platform default.
   */
  columnClassName?: string;
  /**
   * Gap between columns in the kanban board (a Tailwind gap-* class, e.g.
   * "gap-3"). Defaults to the platform's own spacing when omitted.
   */
  columnGapClassName?: string;
  /**
   * Override the scrollable card-list area inside each column entirely
   * (replaces the platform default `"mt-2 min-h-0 flex-1 space-y-2
   * overflow-y-auto pr-1"`). Use when a skin's own column has no outer
   * padding of its own and expects this inner area to carry it instead.
   */
  columnContentClassName?: string;
  /**
   * Override the "no entities in this lane" placeholder's className entirely
   * (replaces the platform default dashed-border box).
   */
  columnEmptyClassName?: string;
  /**
   * 'scroll' (default): columns render in a horizontally-scrolling row at a
   * fixed width each (today's exact behavior).
   * 'grid': columns render in a CSS grid that fills the available width
   * equally (no horizontal scroll) — use when a skin's design has a fixed,
   * known column count and wants them to fill the screen like the platform's
   * generic scroll layout was never designed to.
   */
  boardLayout?: 'scroll' | 'grid';
  /**
   * 'card' (default): the whole kanban board renders inside the platform's
   * bordered/shadowed white Card component.
   * 'plain': the Card chrome is omitted — use when a skin's page background
   * already matches the column background and the extra card border/shadow
   * would be a visible, unwanted seam.
   */
  boardChrome?: 'card' | 'plain';
  /**
   * className applied to the Pipeline page's own root wrapper, on top of the
   * platform's own app-layout content padding (`p-4 lg:px-12 lg:py-8`).
   * Include a matching negative margin (e.g. `"-m-4 lg:-mx-12 lg:-my-8
   * px-7 py-7"`) to cancel that ancestor padding and apply the skin's own
   * instead — scoped to this one page, so other platform routes (Settings,
   * Records, etc.) the skin's nav may still link to keep their normal
   * padding untouched.
   */
  pagePaddingClassName?: string;
  /**
   * Whitelist of state names to show as board columns.
   * States not in this list are hidden from the kanban view.
   * When omitted all non-terminal states are shown.
   */
  displayStates?: string[];
  /**
   * Order of cards within each kanban column, by time spent in the current
   * state. 'oldest' (default) preserves the original API order — a common
   * FIFO-queue convention. 'newest' shows the most recently moved-into-state
   * entities first.
   */
  cardSortOrder?: 'oldest' | 'newest';

  /**
   * Optional client-side visibility gate applied to every entity before it
   * reaches the board/list views — e.g. hiding entities from a queue based
   * on the signed-in user's role. Purely additive: omitting this field
   * means every entity is shown, identical to today's behavior.
   */
  filterVisibleEntities?: (entity: WorkflowEntityState, user: UserPublic | null) => boolean;

  // --- Filter bar -----------------------------------------------------------

  /**
   * Filter controls rendered in the board header.
   * Omitting this field (or providing an empty array) hides the filter bar.
   */
  filterBar?: FilterBarItem[];

  /**
   * Dot-path into entity.data that holds the attachment URL used as the card
   * thumbnail (e.g. ``"photos.0.url"``). When set, the board will call
   * ``GET /entity-records/{id}/thumbnail-url?field=<value>`` to obtain a
   * fresh URL whenever the displayed image fails to load.
   */
  thumbnailDataField?: string;

  /**
   * When set, the board polls for fresh entities on this interval (ms),
   * in addition to refetching after user-triggered actions — for boards
   * where many users work the same entities concurrently and need to see
   * each other's changes (e.g. a claimed ticket disappearing) without
   * waiting for their own next action. Unset (default) disables polling.
   */
  pollIntervalMs?: number;

  // --- Detail view ----------------------------------------------------------

  /**
   * How to open entity detail.
   *   'slideover' — overlay panel on top of the board (default)
   *   'page'      — navigate to a dedicated full-page route
   */
  detailView?: 'slideover' | 'page';

  /**
   * Action buttons shown in the entity detail view header.
   * Each button is only rendered when its triggerName is available from the
   * entity's current state.
   */
  actionButtons?: ActionButtonConfig[];
}

// ---------------------------------------------------------------------------
// Entity views
// ---------------------------------------------------------------------------

/** A named group of fields for structured detail view layout */
export interface FieldGroup {
  /** Section heading shown above the grouped fields */
  label: string;
  /**
   * Field source keys belonging to this group.
   * Each entry must match a `FieldMapping.source` in detailFields.
   */
  fields: string[];
}

/** Formatting hint for a single entity field */
export interface FieldMapping {
  /** Key in entity.data */
  source: string;
  /** Human-readable label */
  label: string;
  /** Formatting type — controls how the value is rendered */
  type?: 'text' | 'email' | 'phone' | 'date' | 'currency' | 'badge';
}

/** Describes how to display entities of one type across views */
export interface EntityViewConfig {
  /** Entity type this view config applies to */
  entityType: string;
  /** Fields shown in list / card views */
  listFields: FieldMapping[];
  /** Fields shown in detail views */
  detailFields: FieldMapping[];
  /** Primary display field used as the entity title */
  titleField: string;
  /** Secondary display field used as the entity subtitle */
  subtitleField?: string;
  /**
   * Named sections for the detail view.
   * When provided, fields are grouped under their section headings.
   * Fields not assigned to any group appear in a generic "Details" section.
   */
  detailFieldGroups?: FieldGroup[];
  /**
   * Fields to hide from all views (e.g. internal / technical fields that
   * should not be visible to end users).
   */
  hiddenFields?: string[];
  /**
   * The entity.data key whose value is the human-readable sequential
   * identifier (e.g. "incident_number" renders as "#007").
   * When omitted the entity's UUID is used.
   */
  displayIdField?: string;
}

// ---------------------------------------------------------------------------
// Custom pages
// ---------------------------------------------------------------------------

/**
 * A skin-provided page mounted at a specific route inside the protected layout.
 * Add entries here and register them in `SkinManifest.customPages` to inject
 * new top-level pages without modifying the platform router.
 */
export interface CustomPageConfig {
  /**
   * Route path the page is mounted at (e.g. '/analytics').
   * Must be unique across all skins and must not clash with platform routes.
   */
  path: string;
  /** Page component rendered inside AppLayout when the route is active. */
  component: React.ComponentType;
  /**
   * When true, the top bar's global entity filter stays visible on this page,
   * the same as on the platform's own client-facing routes (/workflows,
   * /pipeline, /records, /dashboard). Use for custom pages that are scoped to
   * one anchor record; leave unset for pages the filter has no meaning on.
   */
  showGlobalFilter?: boolean;
}

// ---------------------------------------------------------------------------
// State machine (from backend)
// ---------------------------------------------------------------------------

/** State machine definition returned by the backend API */
export interface StateMachineDefinition {
  initial_state: string;
  states: string[];
  terminal_states?: string[];
  transitions: Array<{
    trigger: string;
    from: string | string[];
    to: string;
    guards?: string[];
  }>;
  sla_config?: Record<string, { hours: number }>;
}

// ---------------------------------------------------------------------------
// Skin manifest (root)
// ---------------------------------------------------------------------------

/** Complete skin configuration — single source of truth for one deployment */
export interface SkinManifest {
  /**
   * Unique skin identifier.
   * Must match the `skinId` prop passed to <SkinProvider>.
   */
  id: string;
  /** Product identity, legal copy, and logo assets */
  branding: BrandingConfig;
  /** Sidebar navigation items */
  navigation: NavItem[];
  /** Entity types managed by this deployment */
  entityTypes: EntityTypeConfig[];
  /** Board / pipeline configuration */
  board: BoardConfig;
  /** Per-entity-type view configurations */
  entityViews: EntityViewConfig[];
  /** Named static option lists for select / autocomplete inputs */
  staticLists: Record<string, string[]>;
  /**
   * Skin-level theme defaults applied when an organization has not yet saved
   * its own theme. Values here sit between the global `DEFAULT_THEME` and any
   * per-org overrides, so org admins can still override them via Settings.
   *
   * Use this to enforce deployment-specific branding (e.g. a custom font or
   * brand color) without hardcoding it into the shared global defaults.
   *
   * @example { fontId: 'helvetica-neue', brandColor: '#B8172E' }
   */
  defaultTheme?: Partial<OrgTheme>;
  /**
   * Custom React components injected by the skin into named platform slots.
   * When a slot has a registered component it replaces the platform default.
   * @example { 'entity-detail-view': IncidentDetailView }
   */
  components?: SkinComponents;
  /**
   * Skin-provided pages injected into the protected router.
   * Each entry registers one route inside the AppLayout without touching
   * the platform's own App.tsx route list.
   *
   * The path must not clash with platform routes (/settings, /workflows,
   * /records, /pipeline/:id, /dashboard, /funnel).
   *
   * @example [{ path: '/analytics', component: AnalyticsPage }]
   */
  customPages?: CustomPageConfig[];
  /**
   * When true, the platform's top bar (sidebar trigger, breadcrumbs, agent
   * toggle, notification bell) is hidden on every route. Use when a skin's
   * own sidebar already carries all necessary navigation and branding, and
   * the platform chrome would be redundant.
   */
  hideTopBar?: boolean;
  /**
   * Where "/" and unmatched routes redirect to after login.
   *   'workflows' (default) — the platform's generic entity-list page.
   *   'pipeline' — the skin's board (first live workflow's /pipeline/:id),
   *   for skins whose board is the primary landing surface.
   *   any other string — an arbitrary route path the skin owns (typically
   *   registered via `customPages`), for skins with their own dedicated
   *   landing/dashboard page.
   */
  homePath?: 'workflows' | 'pipeline' | (string & {});
  /**
   * Settings tabs this deployment opts into, by tab id.
   *
   * A few Settings sections only make sense for deployments built around a
   * shared library of reusable fields, so the platform hides them by default
   * rather than showing every deployment a section it has no use for. A skin
   * lists the ids it wants; anything not listed stays hidden, and permissions
   * still apply on top of this.
   *
   * See `OPTIONAL_SETTINGS_TABS` in pages/settings/lib/constant.ts for which
   * tabs are gated this way.
   *
   * @example ['fields', 'methods']
   */
  optionalSettingsTabs?: string[];
}
