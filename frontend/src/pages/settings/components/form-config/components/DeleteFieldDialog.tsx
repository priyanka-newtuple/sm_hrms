import { Button } from '@/components/ui/button';
import type { FormField } from '../../../../../core/types';

interface DeleteFieldDialogProps {
  field: FormField;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function DeleteFieldDialog({ field, onConfirm, onCancel }: DeleteFieldDialogProps) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-card rounded-xl shadow-xl w-full max-w-sm mx-4 p-6">
        <h3 className="text-lg font-semibold text-foreground mb-2">Delete Field</h3>
        <p className="text-sm text-muted-foreground mb-4">
          Delete field &quot;<span className="font-medium">{field.label}</span>&quot;? This cannot be undone.
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
            Delete
          </Button>
        </div>
      </div>
    </div>
  );
}
