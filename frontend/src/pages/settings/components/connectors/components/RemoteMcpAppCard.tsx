/** Binds one catalog entry to its matching server row (if any) and wires its tile to the real API. */

import { useState } from 'react';
import { toast } from 'sonner';

import { useRemoteMcpServerActions } from '@/core/hooks/useRemoteMcpServers';
import type { RemoteMcpAppDefinition, RemoteMcpServer } from '@/core/types';

import RemoteMcpServerTile, { type RemoteMcpTileStatus } from './RemoteMcpServerTile';

interface RemoteMcpAppCardProps {
  app: RemoteMcpAppDefinition;
  servers: RemoteMcpServer[];
  onServersChange: () => Promise<void>;
}

export default function RemoteMcpAppCard({ app, servers, onServersChange }: RemoteMcpAppCardProps) {
  const { create, authorize, remove, discover } = useRemoteMcpServerActions();
  const [pending, setPending] = useState(false);
  const Icon = app.icon;

  const existing = servers.find((s) => s.auth_config?.preset === app.id);
  const status: RemoteMcpTileStatus = pending ? 'connecting' : (existing?.status ?? 'configured');

  const handleConnect = async () => {
    setPending(true);
    try {
      const server = existing ?? (await create({ name: app.name, preset: app.id }));
      const { authorization_url } = await authorize(server.id);
      window.location.href = authorization_url;
      // Full-page navigation follows on success; `pending` only needs
      // resetting on the failure path below.
    } catch (err) {
      setPending(false);
      toast.error(err instanceof Error ? err.message : `Failed to connect ${app.name}.`);
    }
  };

  const handleDisconnect = async () => {
    if (!existing) return;
    setPending(true);
    try {
      await remove(existing.id);
      await onServersChange();
      toast.success(`${app.name} disconnected.`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : `Failed to disconnect ${app.name}.`);
    } finally {
      setPending(false);
    }
  };

  const handleRefresh = async () => {
    if (!existing) return;
    setPending(true);
    try {
      const result = await discover(existing.id);
      await onServersChange();
      if (!result.ok) toast.error(result.error ?? `Could not refresh ${app.name}'s tools.`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : `Failed to refresh ${app.name}.`);
    } finally {
      setPending(false);
    }
  };

  return (
    <RemoteMcpServerTile
      name={app.name}
      description={app.description}
      icon={<Icon className="h-9 w-9 text-foreground drop-shadow-[0_2px_3px_rgba(15,23,42,0.25)]" />}
      status={status}
      toolCount={existing?.tool_count}
      lastError={existing?.last_error}
      onConnect={handleConnect}
      onReconnect={handleConnect}
      onDisconnect={handleDisconnect}
      onRefresh={handleRefresh}
    />
  );
}
