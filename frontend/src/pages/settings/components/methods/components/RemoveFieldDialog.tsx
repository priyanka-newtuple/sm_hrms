/**
 * RemoveFieldDialog
 *
 * Removing a field from a method is not deleting the field: it stays in the
 * Field Library, and earlier method versions still list it. The Forms tab's own
 * DeleteFieldDialog says "cannot be undone", which would be wrong here, so this
 * is a separate dialog rather than a reuse.
 */

import { Button } from '@/components/ui/button';

interface RemoveFieldDialogProps {
  fieldLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  itemLabel?: string;
  parentLabel?: string;
  libraryLabel?: string;
}

export default function RemoveFieldDialog({
  fieldLabel,
  onConfirm,
  onCancel,
  itemLabel = 'Field',
  parentLabel = 'form',
  libraryLabel = 'Field Library',
}: RemoveFieldDialogProps) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-card rounded-xl shadow-xl w-full max-w-sm mx-4 p-6">
        <h3 className="text-lg font-semibold text-foreground mb-2">Remove {itemLabel}</h3>
        <p className="text-sm text-muted-foreground mb-4">
          Remove &quot;<span className="font-medium">{fieldLabel}</span>&quot; from this {parentLabel}? It stays in the {libraryLabel}, and
          earlier versions keep it.
        </p>
        <div className="flex items-center justify-end gap-3">
          <Button variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            variant="ghost"
            onClick={onConfirm}
            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
          >
            Remove
          </Button>
        </div>
      </div>
    </div>
  );
}
