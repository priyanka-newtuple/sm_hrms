import type { FrontendApiEndpoint } from './generated/frontendApiInventory';

export interface BackendApiEndpoint {
  method: string;
  path: string;
  summary?: string;
  operationId?: string;
  tags: string[];
  group: string;
}

export interface ApiCoverageRow {
  frontend: FrontendApiEndpoint;
  status: 'covered' | 'adjacent' | 'missing';
  exactMatches: BackendApiEndpoint[];
  adjacentMatches: BackendApiEndpoint[];
}

export interface ApiCoverageReport {
  rows: ApiCoverageRow[];
  backendEndpoints: BackendApiEndpoint[];
  summary: {
    covered: number;
    adjacent: number;
    missing: number;
    totalExpected: number;
    totalBackend: number;
  };
}

const SERVICE_GROUP_HINTS: Record<string, string[]> = {
  stateMachines: ['metadata_registry', 'entities'],
  funnels: ['metadata_registry', 'projections'],
  formSchemas: ['forms', 'metadata_registry'],
  picklists: [],
  integrations: ['integrations', 'integrations_calendar'],
  users: ['auth', 'identity_access'],
  invitations: [],
  organizations: ['organizations', 'tenants'],
  roles: ['auth', 'identity_access'],
  documentTypes: ['documents'],
  jobs: ['background_jobs', 'intake', 'tasks'],
  llmConfig: ['llm'],
  emailConfig: ['communications', 'collaboration'],
  transcriptionConfig: ['transcription'],
  aiFeatures: [],
  agent: ['agent_ai', 'agents'],
  agentTraces: [],
};

const DOMAIN_KEYWORDS: Record<string, string[]> = {
  stateMachines: ['state machine', 'lifecycle', 'funnel'],
  funnels: ['funnel', 'pipeline', 'lifecycle'],
  formSchemas: ['form', 'schema', 'metadata'],
  picklists: ['picklist'],
  integrations: ['integration', 'calendar', 'event', 'connect'],
  users: ['user', 'auth', 'identity'],
  invitations: ['invitation'],
  organizations: ['organization', 'tenant'],
  roles: ['role', 'permission', 'identity'],
  documentTypes: ['document', 'extract'],
  jobs: ['job', 'task', 'intake'],
  llmConfig: ['llm', 'model'],
  emailConfig: ['email'],
  transcriptionConfig: ['transcription'],
  aiFeatures: ['ai feature', 'model'],
  agent: ['agent', 'tool', 'session'],
  agentTraces: ['trace', 'run'],
};

export async function fetchBackendOpenApi(): Promise<BackendApiEndpoint[]> {
  const response = await fetch('/api/openapi.json');
  if (!response.ok) {
    throw new Error(`Failed to load OpenAPI: ${response.status} ${response.statusText}`);
  }

  const spec = await response.json() as {
    paths?: Record<string, Record<string, {
      summary?: string;
      operationId?: string;
      tags?: string[];
    }>>;
  };

  const endpoints: BackendApiEndpoint[] = [];

  for (const [path, operations] of Object.entries(spec.paths ?? {})) {
    for (const [method, operation] of Object.entries(operations)) {
      endpoints.push({
        method: method.toUpperCase(),
        path,
        summary: operation.summary,
        operationId: operation.operationId,
        tags: operation.tags ?? [],
        group: inferBackendGroup(path, operation.tags ?? []),
      });
    }
  }

  return endpoints.sort((left, right) => {
    if (left.group !== right.group) {
      return left.group.localeCompare(right.group);
    }
    if (left.path !== right.path) {
      return left.path.localeCompare(right.path);
    }
    return left.method.localeCompare(right.method);
  });
}

export function buildApiCoverageReport(
  frontendEndpoints: FrontendApiEndpoint[],
  backendEndpoints: BackendApiEndpoint[],
): ApiCoverageReport {
  const rows = frontendEndpoints.map((frontend) => {
    const normalizedFrontendPath = normalizePath(frontend.path);
    const exactMatches = backendEndpoints.filter((backend) => (
      backend.method === frontend.method
      && normalizePath(backend.path) === normalizedFrontendPath
    ));

    const adjacentMatches = exactMatches.length > 0
      ? []
      : backendEndpoints.filter((backend) => isAdjacent(frontend, backend));

    const status: ApiCoverageRow['status'] = exactMatches.length > 0
      ? 'covered'
      : adjacentMatches.length > 0
        ? 'adjacent'
        : 'missing';

    return {
      frontend,
      status,
      exactMatches,
      adjacentMatches,
    };
  });

  return {
    rows,
    backendEndpoints,
    summary: {
      covered: rows.filter((row) => row.status === 'covered').length,
      adjacent: rows.filter((row) => row.status === 'adjacent').length,
      missing: rows.filter((row) => row.status === 'missing').length,
      totalExpected: frontendEndpoints.length,
      totalBackend: backendEndpoints.length,
    },
  };
}

export function normalizePath(path: string): string {
  const raw = path
    .replace(/^\/v1\/api(?=\/|$)/, '')
    .replace(/\$\{.*\}/g, '');
  const [pathname] = raw.split('?');
  return pathname
    .replace(/\$\{[^}]+\}/g, '{param}')
    .replace(/\{[^}]+\}/g, '{param}')
    .replace(/`/g, '')
    .replace(/\/+/g, '/')
    .replace(/\/$/, '') || '/';
}

function inferBackendGroup(path: string, tags: string[]): string {
  if (tags.length > 0) {
    return tags[0]!.toLowerCase();
  }

  const trimmed = path.replace(/^\/v1\/api\//, '').replace(/^\//, '');
  const [first] = trimmed.split('/');
  return first || 'system';
}

function isAdjacent(frontend: FrontendApiEndpoint, backend: BackendApiEndpoint): boolean {
  const hints = SERVICE_GROUP_HINTS[frontend.serviceGroup] ?? [];
  const normalizedPath = backend.path.toLowerCase();
  const backendGroup = backend.group.toLowerCase();

  if (hints.some((hint) => backendGroup.includes(hint) || normalizedPath.includes(`/${hint}`))) {
    return true;
  }

  const keywords = DOMAIN_KEYWORDS[frontend.serviceGroup] ?? [];
  const haystack = `${backend.path} ${backend.summary ?? ''} ${backend.operationId ?? ''} ${backend.tags.join(' ')}`.toLowerCase();
  return keywords.some((keyword) => haystack.includes(keyword));
}
