import { useEffect, useRef, useState, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { cn } from '../../lib/utils';
import { Button } from '@/components/ui/button';

type FormDialogSize = 'sm' | 'md' | 'lg' | 'xl';

interface FormDialogProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  icon?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size?: FormDialogSize;
  showClose?: boolean;
  closeOnBackdrop?: boolean;
  contentClassName?: string;
  bodyClassName?: string;
}

const sizeClasses: Record<FormDialogSize, string> = {
  sm: 'max-w-md',
  md: 'max-w-lg',
  lg: 'max-w-3xl',
  xl: 'max-w-4xl',
};

export default function FormDialog({
  open,
  onClose,
  title,
  subtitle,
  icon,
  children,
  footer,
  size = 'md',
  showClose = true,
  closeOnBackdrop = true,
  contentClassName,
  bodyClassName,
}: FormDialogProps) {
  // isVisible keeps the DOM mounted during the close animation.
  // It turns on immediately when open=true (derived in render),
  // and turns off after a 200ms delay when open=false (in effect).
  const [isVisible, setIsVisible] = useState(open);
  const [isAnimating, setIsAnimating] = useState(false);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  // Synchronous derived state during render (no effect needed)
  if (open && !isVisible) {
    setIsVisible(true);
  }
  if (!open && isAnimating) {
    setIsAnimating(false);
  }

  useEffect(() => {
    if (open) {
      clearTimeout(closeTimerRef.current);
      requestAnimationFrame(() => setIsAnimating(true));
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = 'unset';
      };
    } else {
      closeTimerRef.current = setTimeout(() => setIsVisible(false), 200);
      document.body.style.overflow = 'unset';
      return () => clearTimeout(closeTimerRef.current);
    }
  }, [open]);

  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    if (open) {
      document.addEventListener('keydown', handleEscape);
    }

    return () => document.removeEventListener('keydown', handleEscape);
  }, [open, onClose]);

  if (!isVisible) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div
        className={cn(
          'fixed inset-0 bg-foreground/20 backdrop-blur-sm transition-opacity duration-200',
          isAnimating ? 'opacity-100' : 'opacity-0',
        )}
        onClick={closeOnBackdrop ? onClose : undefined}
      />

      <div className="flex min-h-full items-center justify-center p-4">
        <div
          className={cn(
            'relative flex max-h-[90vh] w-full flex-col rounded-2xl border border-border bg-card text-card-foreground shadow-2xl transition-all duration-200 ease-out',
            sizeClasses[size],
            isAnimating
              ? 'translate-y-0 scale-100 opacity-100'
              : 'translate-y-4 scale-95 opacity-0',
            contentClassName,
          )}
        >
          <div className="flex items-start justify-between gap-4 rounded-t-2xl border-b border-border bg-[var(--modal-header-background)] px-6 py-4 text-[var(--modal-header-foreground)]">
            <div className="flex min-w-0 items-start gap-3">
              {icon && (
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-current/15">
                  {icon}
                </div>
              )}
              <div className="min-w-0">
                <h2 className="text-lg font-semibold">{title}</h2>
                {subtitle && <p className="mt-1 text-sm opacity-70">{subtitle}</p>}
              </div>
            </div>
            {showClose && (
              <Button
                variant="ghost"
                onClick={onClose}
                className="rounded-lg p-2 opacity-70 transition-colors hover:bg-current/10 hover:opacity-100"
              >
                <X className="h-5 w-5" />
              </Button>
            )}
          </div>

          <div className={cn('flex-1 overflow-y-auto p-6', bodyClassName)}>{children}</div>

          {footer && <div className="border-t border-border bg-muted/60 px-6 py-4">{footer}</div>}
        </div>
      </div>
    </div>
  );
}

export type { FormDialogProps, FormDialogSize };
