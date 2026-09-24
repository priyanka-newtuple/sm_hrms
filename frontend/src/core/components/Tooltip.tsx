import { useState, useRef, useEffect, type ReactNode } from 'react';

type TooltipPosition = 'top' | 'bottom' | 'left' | 'right';

interface TooltipProps {
  /** The content to display inside the tooltip */
  content: ReactNode;
  /** The element that triggers the tooltip */
  children: ReactNode;
  /** Position of the tooltip relative to the trigger */
  position?: TooltipPosition;
  /** Delay in ms before showing the tooltip */
  delay?: number;
  /** Whether the tooltip is disabled */
  disabled?: boolean;
  /** Additional CSS class for the tooltip container */
  className?: string;
  /** Max width of the tooltip */
  maxWidth?: number;
}

/**
 * A reusable tooltip component that displays on hover.
 * Follows the design pattern established by RequirementTooltip.
 */
export default function Tooltip({
  content,
  children,
  position = 'top',
  delay = 150,
  disabled = false,
  className = '',
  maxWidth = 280,
}: TooltipProps) {
  const [isVisible, setIsVisible] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleMouseEnter = () => {
    if (disabled) return;
    timeoutRef.current = setTimeout(() => {
      setIsVisible(true);
    }, delay);
  };

  const handleMouseLeave = () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    setIsVisible(false);
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  if (disabled || !content) {
    return <>{children}</>;
  }

  // Position classes for tooltip placement
  const positionClasses: Record<TooltipPosition, string> = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
  };

  // Arrow position classes
  const arrowClasses: Record<TooltipPosition, string> = {
    top: 'left-1/2 -translate-x-1/2 -bottom-1.5',
    bottom: 'left-1/2 -translate-x-1/2 -top-1.5',
    left: 'top-1/2 -translate-y-1/2 -right-1.5',
    right: 'top-1/2 -translate-y-1/2 -left-1.5',
  };

  return (
    <div
      className={`relative inline-flex ${className}`}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {children}

      {/* Tooltip */}
      {isVisible && (
        <div
          role="tooltip"
          className={`absolute ${positionClasses[position]} z-50
                     rounded-lg border border-border bg-popover text-popover-foreground text-xs shadow-lg
                     px-2.5 py-1.5 whitespace-normal
                     animate-in fade-in-0 zoom-in-95 duration-150`}
          style={{ maxWidth }}
        >
          {/* Arrow */}
          <div
            className={`absolute ${arrowClasses[position]} h-2.5 w-2.5 rotate-45 border-r border-b border-border bg-popover`}
          />

          {/* Content */}
          <div className="relative">{content}</div>
        </div>
      )}
    </div>
  );
}

/**
 * Simple text tooltip - convenience wrapper for string content
 */
export function TextTooltip({
  text,
  children,
  ...props
}: Omit<TooltipProps, 'content'> & { text: string }) {
  return (
    <Tooltip content={text} {...props}>
      {children}
    </Tooltip>
  );
}
