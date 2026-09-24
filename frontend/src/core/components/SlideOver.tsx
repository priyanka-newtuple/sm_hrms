/**
 * SlideOver Component
 *
 * A modern slide-over panel with glassmorphism backdrop and smooth animations.
 */

import { useEffect, useState, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface SlideOverProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: ReactNode;
  /** Pinned below the scrollable content area — never scrolls */
  footer?: ReactNode;
  /** Panel width: sm=24rem, md=32rem, lg=42rem, xl=56rem, 2xl=70% */
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl';
  /** Optional layout override for the scrollable content region. */
  contentClassName?: string;
}

export default function SlideOver({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
  size = 'md',
  contentClassName,
}: SlideOverProps) {
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
      }, 300);
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
    sm: 'max-w-sm',
    md: 'max-w-lg',
    lg: 'max-w-2xl',
    xl: 'max-w-4xl',
    '2xl': 'max-w-[70vw]',
  };

  return (
    <>
      {/* Glassmorphism Backdrop */}
      <div
        className={`
          fixed inset-0 z-40 bg-foreground/20 backdrop-blur-sm
          transition-opacity duration-300
          ${isAnimating ? 'opacity-100' : 'opacity-0'}
        `}
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className={`
          fixed inset-y-0 right-0 w-full ${sizeClasses[size]}
          z-50 flex flex-col border-l border-border bg-card text-card-foreground shadow-2xl
          transition-transform duration-300 ease-out
          ${isAnimating ? 'translate-x-0' : 'translate-x-full'}
        `}
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-border bg-[var(--modal-header-background)] p-6 text-[var(--modal-header-foreground)]">
          <div>
            <h2 className="text-lg font-semibold">{title}</h2>
            {subtitle && (
              <p className="mt-1 text-sm opacity-70">{subtitle}</p>
            )}
          </div>
          <Button
            variant="ghost"
            onClick={onClose}
            className="
              -mr-2 rounded-full p-2 opacity-70
              hover:bg-current/10 hover:opacity-100
              transition-all duration-150
              focus:outline-none focus-visible:ring-2 focus-visible:ring-ring
            "
          >
            <X className="w-5 h-5" />
          </Button>
        </div>

        {/* Content */}
        <div className={cn('flex-1 overflow-y-auto p-6', contentClassName)}>
          {children}
        </div>

        {/* Footer — pinned, never scrolls */}
        {footer && (
          <div className="border-t border-border bg-card px-6 py-4">
            {footer}
          </div>
        )}
      </div>
    </>
  );
}
