import {
  AlertCircle,
  Braces,
  Check,
  FormInput,
  Loader2,
  X,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import EntityTypeSelect from '../../entity-types/EntityTypeSelect';
import type { NewSchemaForm } from '../types';
import { parseFormJson } from '../jsonConfig';
import { useJsonMode } from '../hooks/useJsonMode';
import type { PortableFormConfig } from '../../../../../core/types/portableForm';

const inputClass =
  'w-full rounded-lg border border-border px-3 py-2 text-sm text-foreground focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt';

interface NewEntityFormModalProps {
  /** The entity type this form attaches to. */
  entityType: string;
  onChangeEntityType: (value: string) => void;
  fieldForm: NewSchemaForm;
  onChangeFieldForm: (form: NewSchemaForm) => void;
  creating: boolean;
  error: string | null;
  canWrite: boolean;
  onCreate: () => void;
  /** Create a field form from a pasted portable JSON config instead of the visual inputs. */
  onCreateJson: (entityType: string, data: PortableFormConfig) => void;
  onClose: () => void;
}

export default function NewEntityFormModal({
  entityType,
  onChangeEntityType,
  fieldForm,
  onChangeFieldForm,
  creating,
  error,
  canWrite,
  onCreate,
  onCreateJson,
  onClose,
}: NewEntityFormModalProps) {
  const { mode, jsonDraft, jsonError, setJsonError, switchMode, updateJsonDraft } = useJsonMode(() =>
    JSON.stringify({ name: fieldForm.name, fields: [] }, null, 2)
  );

  // JSON mode carries the form name inside the draft, so only the entity type is required here.
  const jsonMode = mode === 'json';
  const canCreate =
    canWrite &&
    !creating &&
    Boolean(entityType.trim()) &&
    (jsonMode || Boolean(fieldForm.name.trim()));

  const handleCreate = () => {
    if (!jsonMode) {
      onCreate();
      return;
    }
    try {
      const parsed = parseFormJson(jsonDraft);
      setJsonError(null);
      onCreateJson(entityType, parsed);
    } catch (createError) {
      setJsonError(createError instanceof Error ? createError.message : 'Invalid form JSON.');
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-card rounded-xl shadow-xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h3 className="text-lg font-semibold text-foreground">New Entity Form</h3>
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

          <EntityTypeSelect
            value={entityType}
            onChange={onChangeEntityType}
            required
            helperText="Forms belong to an entity type and are independent of workflows."
          />

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

            {mode === 'visual' ? (
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">
                  Display Name
                </label>
                <input
                  type="text"
                  value={fieldForm.name}
                  onChange={(e) => onChangeFieldForm({ ...fieldForm, name: e.target.value })}
                  placeholder="e.g., Candidate"
                  className={inputClass}
                />
              </div>
            ) : (
              <div className="space-y-2">
                <textarea
                  value={jsonDraft}
                  onChange={(event) => updateJsonDraft(event.target.value)}
                  rows={14}
                  spellCheck={false}
                  className="w-full resize-y rounded-lg border border-border bg-muted/50 px-3 py-2 font-mono text-xs leading-relaxed text-foreground outline-none focus:border-cobalt focus:ring-2 focus:ring-cobalt"
                />
                {jsonError && <p className="text-xs text-destructive">{jsonError}</p>}
                <p className="text-xs text-muted-foreground">
                  JSON contains the form name and fields. Entity type is selected above.
                </p>
              </div>
            )}
        </div>

        <div className="flex items-center justify-end gap-3 p-4 border-t border-border bg-muted/50 rounded-b-xl">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="ghost"
            onClick={handleCreate}
            disabled={!canCreate}
            icon={!creating ? <Check className="w-4 h-4" /> : undefined}
          >
            {creating ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : null}
            Create Form
          </Button>
        </div>
      </div>
    </div>
  );
}
