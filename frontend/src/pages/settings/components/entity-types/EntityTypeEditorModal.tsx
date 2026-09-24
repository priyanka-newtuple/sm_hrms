import { useState } from 'react';
import { AlertCircle, Check, Loader2, X } from 'lucide-react';
import Input, { Textarea } from '../../../../core/components/Input';
import { Button } from '@/components/ui/button';
import type {
  EntityType,
  EntityTypeCreateRequest,
  EntityTypeUpdateRequest,
  FormSchema,
} from '../../../../core/types';
import IdentifierConfigSection from './IdentifierConfigSection';

const NAME_REGEX = /^[a-z][a-z0-9_]*$/;

interface EditorDraft {
  name: string;
  description: string;
  identifierLabel: string;
  identifierTemplate: string;
  identifierErrorMessage: string;
}

function toDraft(entityType: EntityType | null): EditorDraft {
  return {
    name: entityType?.name ?? '',
    description: entityType?.description ?? '',
    identifierLabel: entityType?.schema_definition?.identifier_label ?? '',
    identifierTemplate: entityType?.schema_definition?.identifier_template ?? '',
    identifierErrorMessage: entityType?.schema_definition?.identifier_error_message ?? '',
  };
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  return fallback;
}

interface EntityTypeEditorModalProps {
  /** The entity type being edited, or null when creating a new one. */
  entityType: EntityType | null;
  types: EntityType[];
  schemas: FormSchema[];
  canWrite: boolean;
  onClose: () => void;
  createType: (payload: EntityTypeCreateRequest) => Promise<void>;
  updateType: (name: string, payload: EntityTypeUpdateRequest) => Promise<void>;
}

export default function EntityTypeEditorModal({
  entityType,
  types,
  schemas,
  canWrite,
  onClose,
  createType,
  updateType,
}: EntityTypeEditorModalProps) {
  const isNew = entityType === null;
  const [draft, setDraft] = useState<EditorDraft>(() => toDraft(entityType));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const patch = (changes: Partial<EditorDraft>) => setDraft((prev) => ({ ...prev, ...changes }));

  const handleClose = () => {
    if (saving) return;
    onClose();
  };

  const handleSave = async () => {
    if (saving) return;

    const name = draft.name.trim().toLowerCase();
    const description = draft.description.trim();
    const schema_definition = {
      ...(entityType?.schema_definition ?? {}),
      identifier_label: draft.identifierLabel.trim() || undefined,
      identifier_template: draft.identifierTemplate.trim() || undefined,
      identifier_error_message: draft.identifierErrorMessage.trim() || undefined,
    };

    if (isNew) {
      if (!name) {
        setError('Name is required.');
        return;
      }
      if (!NAME_REGEX.test(name)) {
        setError(
          'Name must be lowercase snake_case and start with a letter. Use only letters, digits, and underscores.',
        );
        return;
      }
    }

    setSaving(true);
    setError(null);

    try {
      if (isNew) {
        await createType({
          name,
          ...(description ? { description } : {}),
          schema_definition,
        });
      } else {
        await updateType(entityType.name, { description, schema_definition });
      }
      onClose();
    } catch (e) {
      setError(getErrorMessage(e, 'Failed to save entity type'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="entity-type-editor-title"
    >
      <div className="bg-card rounded-xl shadow-xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h3 id="entity-type-editor-title" className="text-lg font-semibold text-foreground">
            {isNew ? 'New Entity Type' : `Edit ${entityType?.name ?? 'entity type'}`}
          </h3>
          <Button
            variant="outline"
            type="button"
            onClick={handleClose}
            disabled={saving}
            className="p-1 rounded disabled:opacity-50"
            aria-label="Close editor"
          >
            <X className="w-5 h-5" aria-hidden="true" />
          </Button>
        </div>

        <div className="p-4 space-y-4 max-h-[70vh] overflow-y-auto">
          <Input
            id="entity-type-name"
            label="Name"
            required
            value={draft.name}
            onChange={(e) => patch({ name: e.target.value.trimStart().toLowerCase() })}
            placeholder="application"
            disabled={!isNew || saving}
            helperText={
              isNew
                ? 'Lowercase snake_case. Used as the canonical identifier.'
                : 'Name cannot be changed after creation.'
            }
          />

          <Textarea
            id="entity-type-description"
            label="Description"
            value={draft.description}
            onChange={(e) => patch({ description: e.target.value })}
            placeholder="What does this entity represent?"
            rows={3}
            disabled={saving}
            className="resize-none"
          />

          <IdentifierConfigSection
            entityType={entityType}
            label={draft.identifierLabel}
            template={draft.identifierTemplate}
            errorMessage={draft.identifierErrorMessage}
            onLabelChange={(identifierLabel) => patch({ identifierLabel })}
            onTemplateChange={(identifierTemplate) => patch({ identifierTemplate })}
            onErrorMessageChange={(identifierErrorMessage) => patch({ identifierErrorMessage })}
            types={types}
            schemas={schemas}
            saving={saving}
          />

          {error && (
            <div
              className="flex items-start gap-2 px-3 py-2 bg-destructive-subtle border border-destructive/30 rounded-lg text-sm text-destructive"
              role="alert"
            >
              <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" aria-hidden="true" />
              <span>{error}</span>
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 p-4 border-t border-border bg-muted/50 rounded-b-xl">
          <Button
            type="button"
            variant="outline"
            onClick={handleClose}
            disabled={saving}
            className="px-4 py-2 text-foreground hover:bg-muted rounded-lg transition-colors disabled:opacity-50"
          >
            Cancel
          </Button>

          <Button
            variant="primary"
            type="button"
            onClick={() => void handleSave()}
            disabled={!canWrite || saving}
            className="flex items-center gap-2 px-4 py-2 rounded-lg hover:bg-cobalt-dark transition-colors disabled:opacity-50"
          >
            {saving ? (
              <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
            ) : (
              <Check className="w-4 h-4" aria-hidden="true" />
            )}
            {isNew ? 'Create' : 'Save'}
          </Button>
        </div>
      </div>
    </div>
  );
}
