import { Loader2 } from 'lucide-react';

import Badge from '../../../../../core/components/Badge';
import { Button } from '@/components/ui/button';
import type { McpCapability } from '../../../../../core/types';

interface McpCapabilityRowProps {
  capability: McpCapability;
  /** Connector name (e.g. "GitHub") for a remote-discovered tool, or null for a platform tool. */
  sourceName: string | null;
  busy: boolean;
  onToggle: (capabilityId: string, isEnabled: boolean, requiresApproval: boolean) => void;
}

/** One toggleable tool row: name, source/mutating/approval badges, on-off control. */
export default function McpCapabilityRow({ capability, sourceName, busy, onToggle }: McpCapabilityRowProps) {
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3.5 transition-colors hover:bg-muted/30">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-foreground">{capability.display_name}</span>
          {sourceName && <Badge variant="default">{sourceName}</Badge>}
          <Badge variant={capability.is_mutating ? 'warning' : 'success'}>
            {capability.is_mutating ? 'Mutating' : 'Read-only'}
          </Badge>
          {capability.requires_approval && <Badge variant="warning">Approval</Badge>}
        </div>
        <p className="mt-1 truncate text-sm text-muted-foreground">{capability.description}</p>
      </div>
      <Button
        variant="ghost"
        disabled={!capability.package_enabled || busy}
        onClick={() => onToggle(capability.id, capability.is_enabled, capability.requires_approval)}
        className="min-w-16 rounded-lg border border-border px-3 py-2 text-sm"
      >
        {busy ? (
          <Loader2 className="mx-auto h-4 w-4 animate-spin" />
        ) : capability.is_enabled ? (
          'On'
        ) : (
          'Off'
        )}
      </Button>
    </div>
  );
}
