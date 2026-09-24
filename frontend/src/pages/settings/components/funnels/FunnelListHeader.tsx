import {
  Plus, Loader2, LayoutGrid, ListChecks, ChevronDown, Download, Layers,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from '../../../../components/ui/dropdown-menu';
import { usePermissions } from '../../../../core/hooks/usePermissions';

interface FunnelListHeaderProps {
  activeCount: number;
  draftCount: number;
  loading?: boolean;
  onCreate: (mode: 'canvas' | 'wizard') => void;
  onManageServices: () => void;
}

/**
 * Page header for the workflow (funnel) list page.
 *
 * Renders the page title, a summary of active/draft counts, a loading
 * indicator, a disabled Import button placeholder, and a split-button
 * "New Workflow" control that lets the user choose between the canvas
 * builder and the step-by-step wizard.
 *
 * @param props - {@link FunnelListHeaderProps}
 * @param props.activeCount - number of active (published) workflows.
 * @param props.draftCount - number of draft workflows.
 * @param props.loading - when true, shows an inline spinner next to the actions.
 * @param props.onCreate - called when the user picks a creation mode (wizard or canvas).
 */
export default function FunnelListHeader({
  activeCount,
  draftCount,
  loading,
  onCreate,
  onManageServices,
}: FunnelListHeaderProps) {
  const { hasPermission } = usePermissions();
  const canWrite = hasPermission('workflow:write');

  return (
    <div className="flex items-start justify-between gap-4 mb-5">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Workflows</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          State-machine workflows running in this org.
          {' · '}
          <span className="font-mono">{activeCount} active</span>
          {' · '}
          <span className="font-mono">{draftCount} draft</span>
        </p>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        {loading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
        <Button
          variant="outline"
          onClick={onManageServices}
          icon={<Layers className="w-4 h-4" />}
        >
          Manage services
        </Button>
        <button
          disabled
          className="flex items-center gap-2 rounded-lg border border-border bg-background px-4 py-2 text-sm font-medium text-foreground/70 cursor-not-allowed opacity-60"
        >
          <Download className="w-4 h-4" />
          Import
        </button>
        <div className="flex items-stretch rounded-lg overflow-hidden">
          <button
            onClick={() => onCreate('wizard')}
            disabled={!canWrite}
            className="flex items-center gap-2 bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title={!canWrite ? 'You need workflow:write permission' : undefined}
          >
            <Plus className="w-4 h-4" />
            New Workflow
          </button>
          <DropdownMenu>
            <DropdownMenuTrigger
              disabled={!canWrite}
              className="flex items-center border-l border-primary-foreground/20 bg-primary px-2 py-2 text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ChevronDown className="w-4 h-4" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => onCreate('canvas')} disabled={!canWrite}>
                <LayoutGrid />
                Canvas builder
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onCreate('wizard')} disabled={!canWrite}>
                <ListChecks />
                Step-by-step wizard
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </div>
  );
}
