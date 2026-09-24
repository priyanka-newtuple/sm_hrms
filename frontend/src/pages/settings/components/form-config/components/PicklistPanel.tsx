import { Braces, List, Plus, Pencil, Trash2, Loader2, ChevronDown, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { Picklist } from '../../../../../core/types';

interface PicklistPanelProps {
  picklists: Picklist[];
  expanded: boolean;
  deletingPicklist: string | null;
  canWrite: boolean;
  onToggleExpanded: () => void;
  onCreatePicklist: () => void;
  onEditPicklist: (picklist: Picklist) => void;
  onEditPicklistJson: (picklist: Picklist) => void;
  onDeletePicklist: (picklistId: string) => void;
}

export default function PicklistPanel({
  picklists,
  expanded,
  deletingPicklist,
  canWrite,
  onToggleExpanded,
  onCreatePicklist,
  onEditPicklist,
  onEditPicklistJson,
  onDeletePicklist,
}: PicklistPanelProps) {
  return (
    <div className="bg-card rounded-xl border border-border overflow-hidden">
      <Button
        variant="secondary"
        onClick={onToggleExpanded}
        className="h-auto w-full justify-between rounded-none border-0 px-4 py-4"
      >
        <h3 className="flex items-center gap-2 font-medium text-foreground">
          <List className="w-4 h-4 text-muted-foreground" />
          Picklists
          <span className="text-xs font-normal text-muted-foreground">
            ({picklists.length})
          </span>
        </h3>
        {expanded ? (
          <ChevronDown className="w-4 h-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="w-4 h-4 text-muted-foreground" />
        )}
      </Button>

      {expanded && (
        <div className="border-t border-border p-4 pt-2">
          <div className="space-y-2 mb-3">
            {picklists.length === 0 ? (
              <p className="text-sm text-muted-foreground">No picklists configured</p>
            ) : (
              picklists.map((picklist) => (
                <div
                  key={picklist.id}
                  className="flex items-center justify-between py-2 px-2 rounded hover:bg-muted/50 group"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-foreground truncate">
                      {picklist.name}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {picklist.options.length} options
                    </div>
                  </div>
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Button
                      variant="ghost-action"
                      size="icon"
                      onClick={() => onEditPicklistJson(picklist)}
                      title={canWrite ? 'Edit JSON' : 'View JSON'}
                    >
                      <Braces className="w-3 h-3" />
                    </Button>
                    <Button
                      variant="ghost-action"
                      size="icon"
                      onClick={() => onEditPicklist(picklist)}
                      disabled={!canWrite}
                    >
                      <Pencil className="w-3 h-3" />
                    </Button>
                    <Button
                      variant="ghost-danger"
                      size="icon"
                      onClick={() => onDeletePicklist(picklist.id)}
                      disabled={!canWrite || deletingPicklist === picklist.id}
                    >
                      {deletingPicklist === picklist.id ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <Trash2 className="w-3 h-3" />
                      )}
                    </Button>
                  </div>
                </div>
              ))
            )}
          </div>
          <Button
            variant="outline"
            onClick={onCreatePicklist}
            className="w-full border-dashed"
            disabled={!canWrite}
          >
            <Plus className="w-4 h-4" />
            Add Picklist
          </Button>
        </div>
      )}
    </div>
  );
}
