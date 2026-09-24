import { useLocation, useSearchParams } from 'react-router-dom';
import { useAppLabels, type AppLabels } from './useAppLabels';

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

// Route slugs whose breadcrumb label is a renameable app section. `funnel` and
// `workflows` both map to the Workflows label so the section reads consistently.
const APP_LABEL_SLUGS: Record<string, keyof AppLabels> = {
  dashboard: 'dashboard',
  records: 'records',
  pipeline: 'pipeline',
  funnel: 'workflows',
  workflows: 'workflows',
};

// Slug → human label for known path segments
const SEGMENT_LABELS: Record<string, string> = {
  dashboard:   'Dashboard',
  settings:    'Settings',
  tasks:       'Tasks',
  pipeline:    'Pipeline',
  funnel:      'Workflows',
  records:     'Records',
  'whats-new': "What's New",
  create:      'New',
  edit:        'Edit',
};

// Tab param → human label (avoids needing a separate metadata file)
const TAB_LABELS: Record<string, string> = {
  funnels:       'Funnels',
  machines:      'State Machines',
  forms:         'Forms',
  entities:      'Entities',
  agents:        'Agents',
  jobs:          'Jobs',
  traces:        'Agent Traces',
  coverage:      'API Coverage',
  files:         'Files',
  integrations:  'Integrations',
  users:         'Users',
  roles:         'Roles',
  organizations: 'Organizations',
};

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SHORT_ID_RE = /^[0-9a-z]{10,}$/i;

function toLabel(segment: string): string {
  const decoded = decodeURIComponent(segment);
  if (UUID_RE.test(decoded) || SHORT_ID_RE.test(decoded)) return '';
  return (
    SEGMENT_LABELS[decoded] ??
    decoded.replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  );
}

export function useBreadcrumbs(): BreadcrumbItem[] {
  const { pathname } = useLocation();
  const [searchParams] = useSearchParams();
  const appLabels = useAppLabels();

  const segments = pathname.split('/').filter(Boolean);

  const items: BreadcrumbItem[] = [];

  segments.forEach((seg, i) => {
    const appKey = APP_LABEL_SLUGS[decodeURIComponent(seg)];
    const label = appKey ? appLabels[appKey] : toLabel(seg);
    if (!label) return; // skip IDs / UUIDs

    const href = '/' + segments.slice(0, i + 1).join('/');
    items.push({ label, href });
  });

  // Append ?tab value as final crumb (e.g. settings page)
  const tab = searchParams.get('tab');
  if (tab) {
    const tabLabel = TAB_LABELS[tab] ?? toLabel(tab);
    if (tabLabel) items.push({ label: tabLabel });
  }

  // Last item is current page — no link
  if (items.length > 0) {
    delete items[items.length - 1].href;
  }

  return items;
}
