import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Modal from './Modal';

interface ConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'danger' | 'warning' | 'default';
  loading?: boolean;
}

export default function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'default',
  loading = false,
}: ConfirmDialogProps) {
  const iconStyles = {
    danger:  'bg-destructive/10 text-destructive',
    warning: 'bg-amber-500/10 text-amber-500',
    default: 'bg-primary/10 text-primary',
  };

  return (
    <Modal open={open} onClose={onClose} title={title} size="sm">
      <div className="flex items-start gap-3 pb-2">
        <div className={`shrink-0 rounded-full p-2 ${iconStyles[variant]}`}>
          <AlertTriangle className="w-5 h-5" />
        </div>
        <p className="text-sm text-muted-foreground">{message}</p>
      </div>

      <div className="mt-4 flex justify-end gap-3">
        <Button variant="secondary" onClick={onClose} disabled={loading}>
          {cancelLabel}
        </Button>
        <Button
          variant={variant === 'danger' ? 'danger' : variant === 'warning' ? 'warning' : 'primary'}
          onClick={onConfirm}
          disabled={loading}
        >
          {loading ? 'Processing...' : confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}
