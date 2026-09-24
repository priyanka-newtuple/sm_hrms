/** A single pre-built MCP app tile — logo, status, and the one action available at that status. */

import { type ReactNode } from 'react';
import { RefreshCw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export type RemoteMcpTileStatus = 'configured' | 'connecting' | 'connected' | 'needs_reauth' | 'error';

const STATUS_META: Record<RemoteMcpTileStatus, { label: string; dot: string; pill: string }> = {
  configured: { label: 'Not connected', dot: 'bg-muted-foreground/40', pill: 'bg-muted text-muted-foreground' },
  connecting: { label: 'Connecting…', dot: 'bg-primary animate-pulse', pill: 'bg-primary/10 text-primary' },
  connected: {
    label: 'Connected',
    dot: 'bg-success shadow-[0_0_6px_var(--color-success)]',
    pill: 'bg-success-subtle text-success',
  },
  needs_reauth: { label: 'Needs sign-in', dot: 'bg-warning', pill: 'bg-warning-subtle text-warning' },
  error: { label: 'Error', dot: 'bg-destructive', pill: 'bg-destructive-subtle text-destructive' },
};

interface RemoteMcpServerTileProps {
  name: string;
  description: string;
  icon: ReactNode;
  status: RemoteMcpTileStatus;
  toolCount?: number;
  lastError?: string | null;
  onConnect: () => void;
  onReconnect?: () => void;
  onDisconnect?: () => void;
  onRefresh?: () => void;
}

export default function RemoteMcpServerTile({
  name,
  description,
  icon,
  status,
  toolCount,
  lastError,
  onConnect,
  onReconnect,
  onDisconnect,
  onRefresh,
}: RemoteMcpServerTileProps) {
  const meta = STATUS_META[status];

  return (
    <div className="group relative flex flex-col gap-4 rounded-xl bg-card p-5 shadow-card transition-all duration-300 hover:-translate-y-0.5 hover:shadow-float">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center">{icon}</div>
          <div>
            <p className="text-sm font-semibold leading-none">{name}</p>
            <p className="mt-1.5 text-xs text-muted-foreground">{description}</p>
          </div>
        </div>
        <span
          className={cn(
            'inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium',
            meta.pill,
          )}
        >
          <span className={cn('h-1.5 w-1.5 rounded-full', meta.dot)} />
          {meta.label}
        </span>
      </div>

      <p className="text-xs text-muted-foreground">
        {status === 'connected' && toolCount != null
          ? `${toolCount} tool${toolCount === 1 ? '' : 's'} available to agents.`
          : 'Connect once — every tool it offers becomes available to agents automatically.'}
      </p>

      {(status === 'error' || status === 'needs_reauth') && lastError && (
        <p className={cn('text-xs', status === 'error' ? 'text-destructive' : 'text-warning')}>{lastError}</p>
      )}

      <div className="mt-auto flex items-center gap-2 pt-2">
        {status === 'configured' && (
          <>
            <Button variant="primary" className="cursor-pointer" size="sm" onClick={onConnect}>
              Connect
            </Button>
            <span className="text-[11px] text-muted-foreground">No API key or setup needed</span>
          </>
        )}
        {status === 'connecting' && (
          <Button variant="primary" size="sm" loading disabled>
            Connecting
          </Button>
        )}
        {status === 'connected' && (
          <>
            <Button variant="outline" size="sm" icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={onRefresh}>
              Refresh tools
            </Button>
            <Button variant="ghost-danger" size="sm" onClick={onDisconnect}>
              Disconnect
            </Button>
          </>
        )}
        {status === 'needs_reauth' && (
          <Button variant="warning" size="sm" onClick={onReconnect ?? onConnect}>
            Reconnect
          </Button>
        )}
        {status === 'error' && (
          <Button variant="outline" size="sm" onClick={onRefresh ?? onConnect}>
            Retry
          </Button>
        )}
      </div>
    </div>
  );
}
