import { Braces, X, Check, FormInput, Loader2, Plus, GripVertical } from 'lucide-react';

import { Button } from '@/components/ui/button';
import type { EditingPicklist } from '../types';
import { parsePicklistJson } from '../jsonConfig';
import { useJsonMode } from '../hooks/useJsonMode';

interface EditPicklistModalProps {
  editingPicklist: EditingPicklist;
  saving: boolean;
  canWrite: boolean;
  onChange: (updated: EditingPicklist) => void;
  onSave: (updated?: EditingPicklist) => void;
  onClose: () => void;
  onAddOption: () => void;
  onRemoveOption: (index: number) => void;
  onChangeOption: (index: number, field: 'value' | 'label', value: string) => void;
}

export default function EditPicklistModal({
  editingPicklist,
  saving,
  canWrite,
  onChange,
  onSave,
  onClose,
  onAddOption,
  onRemoveOption,
  onChangeOption,
}: EditPicklistModalProps) {
  const {
    mode,
    jsonDraft,
    jsonError,
    setJsonError,
    switchMode,
    updateJsonDraft,
  } = useJsonMode(() => JSON.stringify({
    name: editingPicklist.name,
    options: editingPicklist.options,
  }, null, 2));

  const handleSave = () => {
    if (mode === 'visual') {
      onSave();
      return;
    }
    try {
      const parsed = parsePicklistJson(jsonDraft);
      setJsonError(null);
      onSave({ ...editingPicklist, ...parsed });
    } catch (saveError) {
      setJsonError(saveError instanceof Error ? saveError.message : 'Invalid picklist JSON.');
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-card rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h3 className="text-lg font-semibold text-foreground">
            {editingPicklist.isNew ? 'New Picklist' : 'Edit Picklist'}
          </h3>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="w-5 h-5" />
          </Button>
        </div>

        <div className="p-4 space-y-4 max-h-[60vh] overflow-y-auto">
          {editingPicklist.isNew && (
            <div className="flex items-center gap-1 rounded-lg bg-muted p-1">
              <Button
                type="button"
                variant={mode === 'visual' ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => switchMode('visual')}
                icon={<FormInput className="h-3.5 w-3.5" />}
                className="flex-1"
              >
                Visual
              </Button>
              <Button
                type="button"
                variant={mode === 'json' ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => switchMode('json')}
                icon={<Braces className="h-3.5 w-3.5" />}
                className="flex-1"
              >
                JSON
              </Button>
            </div>
          )}
          {mode === 'json' && editingPicklist.isNew ? (
            <div className="space-y-2">
              <textarea
                value={jsonDraft}
                onChange={(event) => updateJsonDraft(event.target.value)}
                rows={16}
                spellCheck={false}
                className="w-full resize-y rounded-lg border border-border bg-muted/50 px-3 py-2 font-mono text-xs leading-relaxed text-foreground outline-none focus:border-cobalt focus:ring-2 focus:ring-cobalt"
              />
              {jsonError && <p className="text-xs text-destructive">{jsonError}</p>}
            </div>
          ) : (
            <>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Name</label>
            <input
              type="text"
              value={editingPicklist.name}
              onChange={(e) => onChange({ ...editingPicklist, name: e.target.value })}
              placeholder="e.g., Candidate Source"
              className="w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-cobalt focus:border-cobalt"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-sm font-medium text-foreground">Options</label>
              <Button
                variant="ghost-action"
                size="sm"
                onClick={onAddOption}
                icon={<Plus className="w-3 h-3" />}
                disabled={!canWrite}
              >
                Add Option
              </Button>
            </div>
            <div className="space-y-2">
              {editingPicklist.options.map((option, index) => (
                <div key={index} className="flex items-center gap-2">
                  <GripVertical className="w-4 h-4 text-muted-foreground/60" />
                  <input
                    type="text"
                    value={option.label}
                    onChange={(e) => onChangeOption(index, 'label', e.target.value)}
                    placeholder="Label"
                    className="flex-1 px-3 py-2 border border-border rounded-lg text-sm focus:ring-2 focus:ring-cobalt focus:border-cobalt"
                  />
                  <input
                    type="text"
                    value={option.value}
                    onChange={(e) => onChangeOption(index, 'value', e.target.value)}
                    placeholder="value"
                    className="w-32 px-3 py-2 border border-border rounded-lg text-sm font-mono focus:ring-2 focus:ring-cobalt focus:border-cobalt"
                  />
                  <Button
                    variant="ghost-danger"
                    size="icon"
                    onClick={() => onRemoveOption(index)}
                    disabled={!canWrite || editingPicklist.options.length <= 1}
                  >
                    <X className="w-4 h-4" />
                  </Button>
                </div>
              ))}
            </div>
          </div>
            </>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 p-4 border-t border-border bg-muted/50">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="ghost"
            onClick={handleSave}
            disabled={!canWrite || saving}
            icon={!saving ? <Check className="w-4 h-4" /> : undefined}
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : null}
            {editingPicklist.isNew ? 'Create' : 'Save'}
          </Button>
        </div>
      </div>
    </div>
  );
}
