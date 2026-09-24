import { useState } from 'react';
import { AlertCircle, Loader2, Trash2 } from 'lucide-react';
import Modal from '../../../../core/components/Modal';
import { Button } from '@/components/ui/button';
import type { EntityType } from '../../../../core/types';

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  return fallback;
}

interface DeleteEntityTypeDialogProps {
  target: EntityType | null;
  canWrite: boolean;
  onClose: () => void;
  deleteType: (name: string) => Promise<void>;
}

export default function DeleteEntityTypeDialog({
  target,
  canWrite,
  onClose,
  deleteType,
}: DeleteEntityTypeDialogProps) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleClose = () => {
    if (deleting) return;
    setError(null);
    onClose();
  };

  const handleDelete = async () => {
    if (!target || deleting) return;
    setDeleting(true);
    setError(null);
    try {
      await deleteType(target.name);
      setError(null);
      onClose();
    } catch (e) {
      setError(getErrorMessage(e, 'Failed to delete entity type'));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Modal open={!!target} onClose={handleClose} title="Delete entity type">
      <div className="space-y-4">
        <p className="text-sm text-foreground">
          Delete entity type{' '}
          <code className="bg-muted px-1.5 py-0.5 rounded text-xs font-mono">
            {target?.name}
          </code>
          ? Funnels and forms still referencing it will keep their saved value, but new ones won't
          be able to select it.
        </p>

        {error && (
          <div
            className="flex items-start gap-2 px-3 py-2 bg-destructive-subtle border border-destructive/30 rounded-lg text-sm text-destructive"
            role="alert"
          >
            <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" aria-hidden="true" />
            <span>{error}</span>
          </div>
        )}

        <div className="flex justify-end gap-2">
          <Button
            variant="ghost"
            type="button"
            onClick={handleClose}
            disabled={deleting}
            className="px-4 py-2 text-foreground hover:bg-muted rounded-lg transition-colors disabled:opacity-50"
          >
            Cancel
          </Button>

          <Button
            variant="primary"
            type="button"
            onClick={() => void handleDelete()}
            disabled={!canWrite || deleting}
            className="flex items-center gap-2 px-4 py-2 bg-destructive text-destructive-foreground rounded-lg hover:bg-destructive/90 transition-colors disabled:opacity-50"
          >
            {deleting ? (
              <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
            ) : (
              <Trash2 className="w-4 h-4" aria-hidden="true" />
            )}
            Delete
          </Button>
        </div>
      </div>
    </Modal>
  );
}
