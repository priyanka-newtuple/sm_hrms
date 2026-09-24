/** "Apps" strip above the custom connector list — pre-built remote MCP servers you connect with one click. */

import { REMOTE_MCP_APPS } from '@/core/constants/remoteMcpApps';
import { useRemoteMcpServerList } from '@/core/hooks/useRemoteMcpServers';

import RemoteMcpAppCard from './RemoteMcpAppCard';

export default function McpAppCatalog() {
  // Fetched once here (not per-tile) so adding more catalog entries doesn't
  // multiply network calls — every tile reads its own slice of the same list.
  const { data, refetch } = useRemoteMcpServerList();
  const servers = data?.items ?? [];

  return (
    <div className="mb-8">
      <div className="mb-3">
        <h3 className="text-sm font-semibold">Apps</h3>
        <p className="text-xs text-muted-foreground">
          Pre-built connections. Click Connect and approve access — no fields to fill in.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {REMOTE_MCP_APPS.map((app) => (
          <RemoteMcpAppCard key={app.id} app={app} servers={servers} onServersChange={refetch} />
        ))}
      </div>
    </div>
  );
}
