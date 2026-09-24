import { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, RefreshCcw, Wrench, AlertCircle } from 'lucide-react';

import { mcp } from '../../../../core/services/api';
import { useRemoteMcpServerList } from '../../../../core/hooks/useRemoteMcpServers';
import type { McpCapability, McpToolingOverview } from '../../../../core/types';
import { Button } from '@/components/ui/button';

import McpPackageSection from './components/McpPackageSection';
import McpToolFilterBar, { type McpToolTypeFilter } from './components/McpToolFilterBar';

function matchesToolFilter(capability: McpCapability, search: string, typeFilter: McpToolTypeFilter): boolean {
  if (typeFilter === 'mutating' && !capability.is_mutating) return false;
  if (typeFilter === 'read_only' && capability.is_mutating) return false;
  if (!search.trim()) return true;
  const query = search.trim().toLowerCase();
  return (
    capability.display_name.toLowerCase().includes(query) ||
    capability.description.toLowerCase().includes(query) ||
    capability.capability_key.toLowerCase().includes(query)
  );
}

/**
 * Dedicated management surface for platform-managed MCP server packages and
 * their capabilities. Org admins enable/disable each package and toggle
 * individual tools (with per-tool approval) here; agents then reference the
 * enabled tools from the Agents tab. Drives /mcp/tooling and the two
 * configuration PATCH endpoints.
 */
export default function McpToolsTab() {
  const [tooling, setTooling] = useState<McpToolingOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const loadTooling = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      setTooling(await mcp.getTooling());
    } catch (e) {
      setTooling(null);
      setError(e instanceof Error ? e.message : 'Failed to load MCP tools');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTooling();
  }, [loadTooling]);

  const toggleServerPackage = useCallback(
    async (packageId: string, isEnabled: boolean) => {
      setBusyId(packageId);
      try {
        await mcp.updateServerConfiguration(packageId, { is_enabled: !isEnabled });
        await loadTooling();
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to update package');
      } finally {
        setBusyId(null);
      }
    },
    [loadTooling],
  );

  const toggleCapability = useCallback(
    async (capabilityId: string, isEnabled: boolean, requiresApproval: boolean) => {
      setBusyId(capabilityId);
      try {
        await mcp.updateCapabilityConfiguration(capabilityId, {
          is_enabled: !isEnabled,
          requires_approval: requiresApproval,
        });
        await loadTooling();
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to update capability');
      } finally {
        setBusyId(null);
      }
    },
    [loadTooling],
  );

  // Remote MCP server id → connection name (e.g. "GitHub"), so a discovered
  // tool's namespaced id can be attributed back to the app that surfaced it.
  const { data: remoteMcpServers } = useRemoteMcpServerList();
  const serverNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const server of remoteMcpServers?.items ?? []) map.set(server.id, server.name);
    return map;
  }, [remoteMcpServers]);

  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<McpToolTypeFilter>('all');
  const isFiltering = search.trim() !== '' || typeFilter !== 'all';

  const allCapabilities = tooling?.capabilities ?? [];
  const filteredCapabilities = useMemo(
    () => allCapabilities.filter(c => matchesToolFilter(c, search, typeFilter)),
    [allCapabilities, search, typeFilter],
  );

  const packages = tooling?.packages ?? [];
  const visiblePackages = useMemo(
    () => packages
      .map(serverPackage => ({
        serverPackage,
        capabilities: filteredCapabilities.filter(c => c.server_package_id === serverPackage.id),
      }))
      // Hide a package entirely once filtering leaves it with nothing to show —
      // an empty section just adds scroll for a search that already excluded it.
      // With no active filter every package still renders, including empty ones.
      .filter(({ capabilities }) => !isFiltering || capabilities.length > 0),
    [packages, filteredCapabilities, isFiltering],
  );

  return (
    <div className="space-y-6">
      <header className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cobalt/10 text-cobalt">
          <Wrench className="h-5 w-5" />
        </div>
        <div className="flex-1">
          <h2 className="text-lg font-semibold text-foreground">MCP Servers &amp; Tools</h2>
          <p className="text-sm text-muted-foreground">
            Platform-managed MCP tools available to agents in this organization.
          </p>
        </div>
        <Button
          variant="ghost"
          onClick={() => void loadTooling()}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <RefreshCcw className="h-3.5 w-3.5" />
          Refresh
        </Button>
      </header>

      {error && (
        <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive-subtle p-4 text-sm text-destructive">
          <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading && !tooling ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading MCP tools…
        </div>
      ) : packages.length === 0 ? (
        <p className="text-sm text-muted-foreground">No MCP server packages are available.</p>
      ) : (
        <>
          <McpToolFilterBar
            search={search}
            onSearchChange={setSearch}
            typeFilter={typeFilter}
            onTypeFilterChange={setTypeFilter}
            visibleCount={filteredCapabilities.length}
            totalCount={allCapabilities.length}
          />

          {visiblePackages.length === 0 ? (
            <div className="rounded-xl border border-border bg-card p-8 text-center">
              <p className="text-sm text-muted-foreground">No tools match your search.</p>
            </div>
          ) : (
            visiblePackages.map(({ serverPackage, capabilities }) => (
              <McpPackageSection
                key={serverPackage.id}
                serverPackage={serverPackage}
                capabilities={capabilities}
                serverNameById={serverNameById}
                busyId={busyId}
                onTogglePackage={toggleServerPackage}
                onToggleCapability={toggleCapability}
              />
            ))
          )}
        </>
      )}
    </div>
  );
}
