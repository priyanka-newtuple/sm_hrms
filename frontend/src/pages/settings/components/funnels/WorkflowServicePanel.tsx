import { useState } from 'react';
import { Check, Layers, Loader2, MoreHorizontal, Pencil, Plus, Trash2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Modal from '@/core/components/Modal';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { WorkflowService } from '@/core/types';

interface WorkflowServicePanelProps {
  open: boolean;
  onClose: () => void;
  services: WorkflowService[];
  canWrite: boolean;
  savingService: string | null;
  deletingService: string | null;
  onCreateService: (name: string) => Promise<WorkflowService | null>;
  onRenameService: (serviceId: string, name: string) => Promise<boolean>;
  onDeleteService: (service: WorkflowService) => void;
}

/**
 * Create/rename/delete panel for workflow Services. Mirrors
 * MethodCategoryPanel (settings/components/methods/components) exactly —
 * same layout, same inline-edit and dropdown-menu interactions — since a
 * Service is the same kind of org-scoped name lookup a Method category is.
 */
export default function WorkflowServicePanel({
  open,
  onClose,
  services,
  canWrite,
  savingService,
  deletingService,
  onCreateService,
  onRenameService,
  onDeleteService,
}: WorkflowServicePanelProps) {
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [editing, setEditing] = useState<{ id: string; name: string } | null>(null);

  const submitCreate = async () => {
    const name = newName.trim();
    if (!name) return;
    const result = await onCreateService(name);
    if (result) {
      setNewName('');
      setCreating(false);
    }
  };

  const submitRename = async () => {
    if (!editing) return;
    const name = editing.name.trim();
    if (!name) return;
    if (await onRenameService(editing.id, name)) setEditing(null);
  };

  return (
    <Modal open={open} onClose={onClose} title="Manage services" size="md">
      <div className="space-y-3">
        <div className="flex items-center justify-between rounded-lg border border-border bg-muted/20 px-3 py-2">
        <span className="flex items-center gap-2 text-sm font-medium text-foreground">
          <Layers className="h-4 w-4 text-muted-foreground" />
          {services.length} {services.length === 1 ? 'service' : 'services'}
        </span>
        {canWrite && (
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setCreating((value) => !value)}
            className="h-7 w-7 text-muted-foreground hover:text-foreground"
            title="New service"
          >
            <Plus className="h-3.5 w-3.5" />
          </Button>
        )}
        </div>

      {creating && canWrite && (
        <div className="flex items-center gap-1.5 border-b border-border bg-muted/20 p-2">
          <input
            autoFocus
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') void submitCreate();
              if (event.key === 'Escape') { setCreating(false); setNewName(''); }
            }}
            placeholder="Service name"
            className="min-w-0 flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-sm outline-none focus:border-primary"
          />
          <button type="button" onClick={() => void submitCreate()} disabled={!newName.trim()} className="rounded p-1.5 text-primary hover:bg-primary/10 disabled:opacity-40" title="Create service">
            <Check className="h-3.5 w-3.5" />
          </button>
          <button type="button" onClick={() => { setCreating(false); setNewName(''); }} className="rounded p-1.5 text-muted-foreground hover:bg-muted" title="Cancel">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      <div className="max-h-[min(60vh,520px)] overflow-y-auto rounded-lg border border-border py-1">
        {services.length === 0 ? (
          <p className="px-3 py-3 text-xs text-muted-foreground">No services yet</p>
        ) : (
          services.map((service) => {
            const isEditing = editing?.id === service.service_id;
            const isSaving = savingService === service.service_id;
            const isDeleting = deletingService === service.service_id;
            return (
              <div key={service.service_id} className="group mx-1 flex items-center gap-1 rounded-lg hover:bg-muted/50">
                {isEditing ? (
                  <div className="flex min-w-0 flex-1 items-center gap-1 px-2 py-1">
                    <input
                      autoFocus
                      value={editing.name}
                      onChange={(event) => setEditing({ ...editing, name: event.target.value })}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') void submitRename();
                        if (event.key === 'Escape') setEditing(null);
                      }}
                      className="min-w-0 flex-1 rounded border border-primary/40 bg-card px-2 py-1 text-sm outline-none"
                    />
                    <button type="button" onClick={() => void submitRename()} disabled={isSaving} className="rounded p-1 text-primary hover:bg-primary/10 disabled:opacity-40">
                      {isSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                    </button>
                    <button type="button" onClick={() => setEditing(null)} disabled={isSaving} className="rounded p-1 text-muted-foreground hover:bg-muted">
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ) : (
                  <>
                    <span className="min-w-0 flex-1 truncate px-3 py-2 text-sm text-foreground">{service.name}</span>
                    {canWrite && (
                      <DropdownMenu>
                        <DropdownMenuTrigger
                          render={<button type="button" className="mr-1 rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-muted hover:text-foreground group-hover:opacity-100" title="Service actions" />}
                        >
                          {isDeleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <MoreHorizontal className="h-3.5 w-3.5" />}
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-40">
                          <DropdownMenuItem onClick={() => setEditing({ id: service.service_id, name: service.name })}>
                            <Pencil className="mr-2 h-3.5 w-3.5" /> Rename
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => onDeleteService(service)} className="text-destructive focus:text-destructive">
                            <Trash2 className="mr-2 h-3.5 w-3.5" /> Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                  </>
                )}
              </div>
            );
          })
        )}
      </div>
      </div>
    </Modal>
  );
}
