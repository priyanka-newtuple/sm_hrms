import { useEffect, useMemo, useState } from 'react';
import {
  CheckCircle2,
  Loader2,
  RefreshCw,
  Search,
  Server,
  TriangleAlert,
  XCircle,
} from 'lucide-react';
import AlertBanner from '../../../../core/components/AlertBanner';
import Badge from '../../../../core/components/Badge';
import { Button } from '@/components/ui/button';
import Input from '../../../../core/components/Input';
import Panel, { PanelHeader } from '../../../../core/components/Panel';
import SectionHeader from '../../../../core/components/SectionHeader';
import { frontendApiInventory } from '../../../../domains/ats/settings/generated/frontendApiInventory';
import {
  buildApiCoverageReport,
  fetchBackendOpenApi,
  type ApiCoverageReport,
  type BackendApiEndpoint,
} from '../../../../domains/ats/settings/apiCoverage';

type StatusFilter = 'all' | 'covered' | 'adjacent' | 'missing';

const STATUS_META = {
  covered: {
    label: 'Green',
    badgeVariant: 'success' as const,
    icon: CheckCircle2,
  },
  adjacent: {
    label: 'Amber',
    badgeVariant: 'warning' as const,
    icon: TriangleAlert,
  },
  missing: {
    label: 'Red',
    badgeVariant: 'error' as const,
    icon: XCircle,
  },
};

function groupBackendEndpoints(endpoints: BackendApiEndpoint[]) {
  const groups = new Map<string, BackendApiEndpoint[]>();
  for (const endpoint of endpoints) {
    const current = groups.get(endpoint.group) ?? [];
    current.push(endpoint);
    groups.set(endpoint.group, current);
  }
  return Array.from(groups.entries()).sort(([left], [right]) => left.localeCompare(right));
}

export default function ApiCoverageTab() {
  const [report, setReport] = useState<ApiCoverageReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [search, setSearch] = useState('');

  const loadReport = async () => {
    try {
      setLoading(true);
      setError(null);
      const backendEndpoints = await fetchBackendOpenApi();
      setReport(buildApiCoverageReport(frontendApiInventory, backendEndpoints));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load API coverage');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReport();
  }, []);

  const filteredRows = useMemo(() => {
    if (!report) {
      return [];
    }

    const query = search.trim().toLowerCase();

    return report.rows.filter((row) => {
      if (statusFilter !== 'all' && row.status !== statusFilter) {
        return false;
      }

      if (!query) {
        return true;
      }

      const text = [
        row.frontend.serviceLabel,
        row.frontend.methodName,
        row.frontend.method,
        row.frontend.path,
        row.frontend.sourceFile,
        ...row.exactMatches.map((endpoint) => endpoint.path),
        ...row.adjacentMatches.map((endpoint) => endpoint.path),
      ].join(' ').toLowerCase();

      return text.includes(query);
    });
  }, [report, search, statusFilter]);

  const backendGroups = useMemo(
    () => groupBackendEndpoints(report?.backendEndpoints ?? []),
    [report],
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 text-cobalt animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <SectionHeader
        title="API Coverage"
        description="Live comparison between the settings frontend contract and modular backend OpenAPI"
        icon={<Server className="w-5 h-5" />}
        actions={(
          <Button variant="ghost" onClick={loadReport} icon={<RefreshCw className="w-4 h-4" />}>
            Refresh
          </Button>
        )}
      />

      {error && (
        <AlertBanner tone="error" title="OpenAPI load failed">
          {error}
        </AlertBanner>
      )}

      {report && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <SummaryCard label="Green" value={report.summary.covered} tone="success" helper="Exact frontend/backend match" />
            <SummaryCard label="Amber" value={report.summary.adjacent} tone="warning" helper="Adjacent backend capability only" />
            <SummaryCard label="Red" value={report.summary.missing} tone="error" helper="No current backend support" />
            <SummaryCard label="Backend Endpoints" value={report.summary.totalBackend} tone="cobalt" helper="Live FastAPI OpenAPI inventory" />
          </div>

          <Panel>
            <div className="flex flex-col md:flex-row md:items-center gap-3 justify-between">
              <div className="flex flex-wrap items-center gap-2">
                {(['all', 'covered', 'adjacent', 'missing'] as StatusFilter[]).map((filter) => (
                  <Button variant="primary"
                    key={filter}
                    onClick={() => setStatusFilter(filter)}
                    className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                      statusFilter === filter
                        ? 'bg-cobalt text-white'
                        : 'bg-muted text-muted-foreground hover:bg-accent'
                    }`}
                  >
                    {filter === 'all' ? 'All statuses' : STATUS_META[filter].label}
                  </Button>
                ))}
              </div>
              <div className="w-full md:w-96">
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search endpoint, domain, or backend route"
                  leftIcon={<Search className="w-4 h-4" />}
                />
              </div>
            </div>
          </Panel>

          <Panel padding="none" overflowHidden>
            <PanelHeader
              title="Frontend Coverage Matrix"
              description={`${filteredRows.length} of ${report.summary.totalExpected} expected endpoints shown`}
            />
            <div className="overflow-x-auto">
              <table className="w-full min-w-[980px]">
                <thead className="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3">Domain</th>
                    <th className="px-4 py-3">Frontend Endpoint</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Backend Match</th>
                    <th className="px-4 py-3">Source</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filteredRows.map((row) => {
                    const statusMeta = STATUS_META[row.status];
                    const StatusIcon = statusMeta.icon;
                    const backendMatches = row.status === 'covered' ? row.exactMatches : row.adjacentMatches;
                    return (
                      <tr key={`${row.frontend.serviceGroup}-${row.frontend.methodName}-${row.frontend.method}-${row.frontend.path}`}>
                        <td className="px-4 py-3 align-top">
                          <div className="font-medium text-foreground">{row.frontend.serviceLabel}</div>
                          <div className="text-xs text-muted-foreground mt-1">{row.frontend.methodName}</div>
                        </td>
                        <td className="px-4 py-3 align-top">
                          <div className="font-mono text-sm text-foreground">{row.frontend.method} {row.frontend.path}</div>
                        </td>
                        <td className="px-4 py-3 align-top">
                          <Badge variant={statusMeta.badgeVariant} size="md" icon={<StatusIcon className="w-3 h-3" />}>
                            {statusMeta.label}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 align-top">
                          {backendMatches.length > 0 ? (
                            <div className="space-y-2">
                              {backendMatches.slice(0, 4).map((endpoint) => (
                                <div key={`${endpoint.method}-${endpoint.path}`}>
                                  <div className="font-mono text-xs text-foreground">{endpoint.method} {endpoint.path}</div>
                                  <div className="text-xs text-muted-foreground mt-0.5">
                                    {endpoint.group}
                                    {endpoint.summary ? ` • ${endpoint.summary}` : ''}
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <span className="text-sm text-muted-foreground">No current backend route</span>
                          )}
                        </td>
                        <td className="px-4 py-3 align-top">
                          <span className="font-mono text-xs text-muted-foreground">{row.frontend.sourceFile}</span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel padding="none" overflowHidden>
            <PanelHeader
              title="Backend Endpoint Inventory"
              description="Raw FastAPI route surface grouped by module prefix or tag"
            />
            <div className="divide-y divide-border">
              {backendGroups.map(([group, endpoints]) => (
                <details key={group} className="group" open>
                  <summary className="list-none cursor-pointer px-4 py-3 flex items-center justify-between hover:bg-muted/50">
                    <div className="flex items-center gap-3">
                      <span className="font-medium text-foreground">{group}</span>
                      <Badge variant="default">{endpoints.length}</Badge>
                    </div>
                    <span className="text-xs text-muted-foreground group-open:hidden">Expand</span>
                    <span className="text-xs text-muted-foreground hidden group-open:inline">Collapse</span>
                  </summary>
                  <div className="px-4 pb-4 space-y-2">
                    {endpoints.map((endpoint) => (
                      <div key={`${endpoint.method}-${endpoint.path}`} className="rounded-lg border border-border bg-muted/50 px-3 py-2">
                        <div className="font-mono text-xs text-foreground">{endpoint.method} {endpoint.path}</div>
                        <div className="text-xs text-muted-foreground mt-1">
                          {endpoint.operationId ?? 'No operationId'}
                          {endpoint.summary ? ` • ${endpoint.summary}` : ''}
                        </div>
                      </div>
                    ))}
                  </div>
                </details>
              ))}
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}

function SummaryCard({
  label,
  value,
  tone,
  helper,
}: {
  label: string;
  value: number;
  tone: 'success' | 'warning' | 'error' | 'cobalt';
  helper: string;
}) {
  return (
    <Panel>
      <Badge variant={tone} size="md">{label}</Badge>
      <div className="mt-3 text-2xl font-semibold text-foreground">{value}</div>
      <p className="mt-1 text-sm text-muted-foreground">{helper}</p>
    </Panel>
  );
}
