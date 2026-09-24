/**
 * NewMethodModal
 *
 * Creates an empty method: name, optional description, optional category.
 * Fields are added afterwards from the Field Library, so there is nothing to
 * configure here beyond identity — which is also why there's no JSON mode like
 * the Forms tab's equivalent has.
 */

import { useState } from 'react';
import { AlertCircle, Check, Loader2, Plus, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { MethodCategory } from '@/core/types';

interface NewMethodModalProps {
  categories: MethodCategory[];
  creating: boolean;
  error: string | null;
  canWrite: boolean;
  onCreate: (payload: { name: string; description: string | null; categoryId: string | null }) => void;
  onCreateCategory: (name: string) => Promise<MethodCategory | null>;
  onClose: () => void;
  entityLabel?: string;
  itemLabelPlural?: string;
  libraryLabel?: string;
}

export default function NewMethodModal({
  categories,
  creating,
  error,
  canWrite,
  onCreate,
  onCreateCategory,
  onClose,
  entityLabel = 'Form',
  itemLabelPlural = 'Fields',
  libraryLabel = 'Field Library',
}: NewMethodModalProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [newCategory, setNewCategory] = useState('');
  const [showNewCategory, setShowNewCategory] = useState(false);
  const [creatingCategory, setCreatingCategory] = useState(false);

  const handleCreateCategory = async () => {
    const trimmed = newCategory.trim();
    if (!trimmed) return;
    setCreatingCategory(true);
    const created = await onCreateCategory(trimmed);
    setCreatingCategory(false);
    if (created) {
      setCategoryId(created.category_id);
      setNewCategory('');
      setShowNewCategory(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-card rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h3 className="text-lg font-semibold text-foreground">New {entityLabel}</h3>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="w-5 h-5" />
          </Button>
        </div>

        <div className="p-4 space-y-4 max-h-[65vh] overflow-y-auto">
          {error && (
            <div className="flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-destructive text-sm">
              <AlertCircle className="w-4 h-4 shrink-0" />
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-foreground mb-1">
              Name <span className="text-destructive">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
              placeholder="e.g., Reagent Preparation"
              className="w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-cobalt focus:border-cobalt"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-foreground mb-1">
              Description <span className="font-normal text-muted-foreground">· optional</span>
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder={`What this ${entityLabel.toLowerCase()} is for, and when to use it`}
              className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:ring-2 focus:ring-cobalt focus:border-cobalt"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-foreground mb-1">
              Category <span className="font-normal text-muted-foreground">· optional</span>
            </label>
            {showNewCategory ? (
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={newCategory}
                  onChange={(e) => setNewCategory(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void handleCreateCategory();
                    if (e.key === 'Escape') setShowNewCategory(false);
                  }}
                  autoFocus
                  placeholder="New category name"
                  className="flex-1 px-3 py-2 border border-border rounded-lg text-sm focus:ring-2 focus:ring-cobalt focus:border-cobalt"
                />
                <Button
                  variant="ghost"
                  onClick={() => void handleCreateCategory()}
                  disabled={creatingCategory || !newCategory.trim()}
                >
                  {creatingCategory ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                </Button>
                <Button variant="ghost" onClick={() => setShowNewCategory(false)}>
                  <X className="w-4 h-4" />
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <select
                  value={categoryId}
                  onChange={(e) => setCategoryId(e.target.value)}
                  className="flex-1 h-10 px-3 border border-border rounded-lg text-sm focus:ring-2 focus:ring-cobalt focus:border-cobalt"
                >
                  <option value="">Uncategorised</option>
                  {categories.map((category) => (
                    <option key={category.category_id} value={category.category_id}>
                      {category.name}
                    </option>
                  ))}
                </select>
                <Button
                  variant="outline"
                  onClick={() => setShowNewCategory(true)}
                  icon={<Plus className="w-3.5 h-3.5" />}
                >
                  New
                </Button>
              </div>
            )}
          </div>

          <p className="text-xs text-muted-foreground">
            {itemLabelPlural} are added after the {entityLabel.toLowerCase()} exists, by picking them from the {libraryLabel}.
          </p>
        </div>

        <div className="flex items-center justify-end gap-3 p-4 border-t border-border bg-muted/50 rounded-b-xl">
          <Button variant="secondary" onClick={onClose} disabled={creating}>
            Cancel
          </Button>
          <Button
            variant="ghost"
            onClick={() =>
              onCreate({
                name: name.trim(),
                description: description.trim() || null,
                categoryId: categoryId || null,
              })
            }
            disabled={!canWrite || creating || !name.trim()}
            icon={!creating ? <Check className="w-4 h-4" /> : undefined}
          >
            {creating ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : null}
            Create {entityLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
