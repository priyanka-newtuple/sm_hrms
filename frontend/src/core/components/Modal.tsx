/**
 * Modal Component
 *
 * A modern modal dialog with glassmorphism backdrop and smooth animations.
 */

import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'full';
  showClose?: boolean;
}

export default function Modal({
  open,
  onClose,
  title,
  children,
  size = 'md',
  showClose = true,
}: ModalProps) {
  const modalRef = useRef<HTMLDivElement>(null);
  const [isVisible, setIsVisible] = useState(open);
  const [isAnimating, setIsAnimating] = useState(false);

  if (open && !isVisible) {
    setIsVisible(true);
  }
  if (!open && isAnimating) {
    setIsAnimating(false);
  }

  useEffect(() => {
    if (open) {
      requestAnimationFrame(() => {
        setIsAnimating(true);
      });
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = 'unset';
      };
    } else {
      const timer = setTimeout(() => {
        setIsVisible(false);
      }, 200);
      document.body.style.overflow = 'unset';
      return () => clearTimeout(timer);
    }
  }, [open]);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };

    if (open) {
      document.addEventListener('keydown', handleEscape);
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [open, onClose]);

  if (!isVisible) return null;

  const sizeClasses = {
    sm: 'max-w-md',
    md: 'max-w-lg',
    lg: 'max-w-2xl',
    xl: 'max-w-5xl',
    full: 'max-w-[95vw] h-[90vh]',
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Glassmorphism Backdrop */}
      <div
        className={`
          fixed inset-0 bg-foreground/20 backdrop-blur-sm
          transition-opacity duration-200
          ${isAnimating ? 'opacity-100' : 'opacity-0'}
        `}
        onClick={onClose}
      />

      {/* Modal Container */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div
          ref={modalRef}
          className={`
            relative w-full ${sizeClasses[size]}
            rounded-2xl border border-border bg-card text-card-foreground shadow-2xl
            transition-all duration-200 ease-out
            ${isAnimating
              ? 'opacity-100 scale-100 translate-y-0'
              : 'opacity-0 scale-95 translate-y-4'
            }
          `}
        >
          {/* Header */}
          <div className="flex items-center justify-between rounded-t-2xl border-b border-border bg-[var(--modal-header-background)] px-6 py-4 text-[var(--modal-header-foreground)]">
            <h2 className="text-lg font-semibold">{title}</h2>
            {showClose && (
              <Button
                variant="ghost"
                size="icon"
                onClick={onClose}
                className="
                  rounded-full p-2 opacity-70
                  hover:bg-current/10 hover:opacity-100
                  transition-all duration-150
                  focus:outline-none focus-visible:ring-2 focus-visible:ring-ring
                "
              >
                <X className="w-5 h-5" />
              </Button>
            )}
          </div>

          {/* Content */}
          <div className="px-6 py-4 max-h-[calc(90vh-120px)] overflow-y-auto">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}
