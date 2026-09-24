import { useMemo, useState } from 'react';
import { Loader2, Power } from 'lucide-react';

import Badge from '../../../../../core/components/Badge';
import { Button } from '@/components/ui/button';
import { parseRemoteMcpServerId } from '../../../../../core/utils';
import type { McpCapability, McpServerPackage } from '../../../../../core/types';

import McpCapabilityRow from './McpCapabilityRow';
import McpConnectorFilter, { ALL_APPS_VALUE, type McpConnectorFilterOption } from './McpConnectorFilter';

interface McpPackageSectionProps {
  serverPackage: McpServerPackage;
  capabilities: McpCapability[];
  /** Remote MCP server id → connection name (e.g. "GitHub"), for attributing each tool. */
  serverNameById: Map<string, string>;
  busyId: string | null;
  onTogglePackage: (packageId: string, isEnabled: boolean) => void;
  onToggleCapability: (capabilityId: string, isEnabled: boolean, requiresApproval: boolean) => void;
}

/** One MCP server package (platform tools, or every connected app's discovered tools) with its own capability list. */
export default function McpPackageSection({
  serverPackage,
  capabilities,
  serverNameById,
  busyId,
  onTogglePackage,
  onToggleCapability,
}: McpPackageSectionProps) {
  const [connectorFilter, setConnectorFilter] = useState<string>(ALL_APPS_VALUE);

  // A tool's source connector, keyed by capability id — computed once per
  // capabilities change rather than re-parsing tool_id on every render.
  const sourceByCapabilityId = useMemo(() => {
    const map = new Map<string, string | null>();
    for (const capability of capabilities) {
      const serverId = parseRemoteMcpServerId(capability.tool_id);
      map.set(capability.id, serverId ? (serverNameById.get(serverId) ?? null) : null);
    }
    return map;
  }, [capabilities, serverNameById]);

  const connectorOptions = useMemo<McpConnectorFilterOption[]>(() => {
    const counts = new Map<string, number>();
    for (const capability of capabilities) {
      const name = sourceByCapabilityId.get(capability.id);
      if (name) counts.set(name, (counts.get(name) ?? 0) + 1);
    }
    return [...counts.entries()]
      .map(([label, count]) => ({ id: label, label, count }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [capabilities, sourceByCapabilityId]);

  // Only worth showing a filter once there's more than one connector to
  // distinguish between — otherwise it's a dropdown with nothing to do.
  const showConnectorFilter = connectorOptions.length > 1;
  const visibleCapabilities =
    showConnectorFilter && connectorFilter !== ALL_APPS_VALUE
      ? capabilities.filter(c => sourceByCapabilityId.get(c.id) === connectorFilter)
      : capabilities;

  return (
    <section className="rounded-xl border border-border bg-card p-4">
      <div className="mb-4 flex items-center justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground">{serverPackage.name}</h3>
            <Badge variant={serverPackage.is_enabled ? 'success' : 'default'}>
              {serverPackage.is_enabled ? 'Enabled' : 'Disabled'}
            </Badge>
            {serverPackage.is_platform_managed ? (
              <Badge variant="default">Platform</Badge>
            ) : (
              <Badge variant="default">Connected app</Badge>
            )}
          </div>
          {serverPackage.description && (
            <p className="mt-1 text-sm text-muted-foreground">{serverPackage.description}</p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {showConnectorFilter && (
            <McpConnectorFilter
              options={connectorOptions}
              totalCount={capabilities.length}
              value={connectorFilter}
              onChange={setConnectorFilter}
            />
          )}
          <Button
            variant="ghost"
            disabled={busyId === serverPackage.id}
            onClick={() => onTogglePackage(serverPackage.id, serverPackage.is_enabled)}
            className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm"
          >
            {busyId === serverPackage.id ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Power className="h-4 w-4" />
            )}
            {serverPackage.is_enabled ? 'Disable package' : 'Enable package'}
          </Button>
        </div>
      </div>

      {capabilities.length === 0 ? (
        <p className="text-sm text-muted-foreground">No tools discovered yet.</p>
      ) : visibleCapabilities.length === 0 ? (
        <p className="text-sm text-muted-foreground">No tools from this app.</p>
      ) : (
        <div className="divide-y divide-border rounded-lg border border-border">
          {visibleCapabilities.map(capability => (
            <McpCapabilityRow
              key={capability.id}
              capability={capability}
              sourceName={sourceByCapabilityId.get(capability.id) ?? null}
              busy={busyId === capability.id}
              onToggle={onToggleCapability}
            />
          ))}
        </div>
      )}
    </section>
  );
}
