import { useState } from 'react';
import { Check, FolderKanban, Loader2, MoreHorizontal, Pencil, Plus, Trash2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Modal from '@/core/components/Modal';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { MethodCategory } from '@/core/types';

interface MethodCategoryPanelProps {
  open: boolean;
  onClose: () => void;
  categories: MethodCategory[];
  canWrite: boolean;
  savingCategory: string | null;
  deletingCategory: string | null;
  onCreateCategory: (name: string) => Promise<MethodCategory | null>;
  onRenameCategory: (categoryId: string, name: string) => Promise<boolean>;
  onDeleteCategory: (category: MethodCategory) => void;
}

export default function MethodCategoryPanel({
  open,
  onClose,
  categories,
  canWrite,
  savingCategory,
  deletingCategory,
  onCreateCategory,
  onRenameCategory,
  onDeleteCategory,
}: MethodCategoryPanelProps) {
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [editing, setEditing] = useState<{ id: string; name: string } | null>(null);

  const submitCreate = async () => {
    const name = newName.trim();
    if (!name) return;
    const result = await onCreateCategory(name);
    if (result) {
      setNewName('');
      setCreating(false);
    }
  };

  const submitRename = async () => {
    if (!editing) return;
    const name = editing.name.trim();
    if (!name) return;
    if (await onRenameCategory(editing.id, name)) setEditing(null);
  };

  return (
    <Modal open={open} onClose={onClose} title="Manage categories" size="md">
      <div className="space-y-3">
        <div className="flex items-center justify-between rounded-lg border border-border bg-muted/20 px-3 py-2">
        <span className="flex items-center gap-2 text-sm font-medium text-foreground">
          <FolderKanban className="h-4 w-4 text-muted-foreground" />
          {categories.length} {categories.length === 1 ? 'category' : 'categories'}
        </span>
        {canWrite && (
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setCreating((value) => !value)}
            className="h-7 w-7 text-muted-foreground hover:text-foreground"
            title="New category"
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
            placeholder="Category name"
            className="min-w-0 flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-sm outline-none focus:border-primary"
          />
          <button type="button" onClick={() => void submitCreate()} disabled={!newName.trim()} className="rounded p-1.5 text-primary hover:bg-primary/10 disabled:opacity-40" title="Create category">
            <Check className="h-3.5 w-3.5" />
          </button>
          <button type="button" onClick={() => { setCreating(false); setNewName(''); }} className="rounded p-1.5 text-muted-foreground hover:bg-muted" title="Cancel">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      <div className="max-h-[min(60vh,520px)] overflow-y-auto rounded-lg border border-border py-1">
        {categories.length === 0 ? (
          <p className="px-3 py-3 text-xs text-muted-foreground">No categories yet</p>
        ) : (
          categories.map((category) => {
            const isEditing = editing?.id === category.category_id;
            const isSaving = savingCategory === category.category_id;
            const isDeleting = deletingCategory === category.category_id;
            return (
              <div key={category.category_id} className="group mx-1 flex items-center gap-1 rounded-lg hover:bg-muted/50">
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
                    <span className="min-w-0 flex-1 truncate px-3 py-2 text-sm text-foreground">{category.name}</span>
                    {canWrite && (
                      <DropdownMenu>
                        <DropdownMenuTrigger
                          render={<button type="button" className="mr-1 rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-muted hover:text-foreground group-hover:opacity-100" title="Category actions" />}
                        >
                          {isDeleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <MoreHorizontal className="h-3.5 w-3.5" />}
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-40">
                          <DropdownMenuItem onClick={() => setEditing({ id: category.category_id, name: category.name })}>
                            <Pencil className="mr-2 h-3.5 w-3.5" /> Rename
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => onDeleteCategory(category)} className="text-destructive focus:text-destructive">
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
