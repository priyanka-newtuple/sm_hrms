import { Button } from '@/components/ui/button';

interface MethodActionDialogProps {
  title: string;
  description: React.ReactNode;
  confirmLabel: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function MethodActionDialog({
  title,
  description,
  confirmLabel,
  busy = false,
  onConfirm,
  onCancel,
}: MethodActionDialogProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="presentation">
      <div className="w-full max-w-sm rounded-xl bg-card p-6 shadow-xl" role="dialog" aria-modal="true" aria-labelledby="method-action-title">
        <h3 id="method-action-title" className="mb-2 text-lg font-semibold text-foreground">{title}</h3>
        <div className="mb-5 text-sm text-muted-foreground">{description}</div>
        <div className="flex items-center justify-end gap-3">
          <Button variant="secondary" onClick={onCancel} disabled={busy}>Cancel</Button>
          <Button
            variant="ghost"
            onClick={onConfirm}
            disabled={busy}
            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
          >
            {busy ? 'Working…' : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
