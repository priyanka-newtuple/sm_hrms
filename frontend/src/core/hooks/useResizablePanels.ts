/**
 * Hook for creating resizable split panels.
 *
 * Usage:
 *   const { leftWidth, isDragging, resizerProps } = useResizablePanels({
 *     initialLeftWidth: 45,
 *     minLeftWidth: 20,
 *     maxLeftWidth: 80,
 *   });
 *
 *   <div style={{ width: `${leftWidth}%` }}>Left</div>
 *   <div {...resizerProps} className="resizer" />
 *   <div style={{ width: `${100 - leftWidth}%` }}>Right</div>
 */

import { useState, useCallback, useEffect, useRef } from 'react';

interface UseResizablePanelsOptions {
  /** Initial width of left panel as percentage (0-100) */
  initialLeftWidth?: number;
  /** Minimum width of left panel as percentage */
  minLeftWidth?: number;
  /** Maximum width of left panel as percentage */
  maxLeftWidth?: number;
  /** Callback when resize completes */
  onResizeEnd?: (leftWidth: number) => void;
}

interface ResizerProps {
  onMouseDown: (e: React.MouseEvent) => void;
  onTouchStart: (e: React.TouchEvent) => void;
}

interface UseResizablePanelsResult {
  /** Current width of left panel as percentage */
  leftWidth: number;
  /** Whether currently dragging */
  isDragging: boolean;
  /** Props to spread on the resizer element */
  resizerProps: ResizerProps;
  /** Reset to initial width */
  reset: () => void;
}

export function useResizablePanels({
  initialLeftWidth = 45,
  minLeftWidth = 20,
  maxLeftWidth = 80,
  onResizeEnd,
}: UseResizablePanelsOptions = {}): UseResizablePanelsResult {
  const [leftWidth, setLeftWidth] = useState(initialLeftWidth);
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLElement | null>(null);
  const startXRef = useRef(0);
  const startWidthRef = useRef(0);

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!isDragging || !containerRef.current) return;

      const containerRect = containerRef.current.getBoundingClientRect();
      const containerWidth = containerRect.width;
      const deltaX = e.clientX - startXRef.current;
      const deltaPercent = (deltaX / containerWidth) * 100;
      const newWidth = Math.min(
        maxLeftWidth,
        Math.max(minLeftWidth, startWidthRef.current + deltaPercent)
      );

      setLeftWidth(newWidth);
    },
    [isDragging, minLeftWidth, maxLeftWidth]
  );

  const handleTouchMove = useCallback(
    (e: TouchEvent) => {
      if (!isDragging || !containerRef.current) return;

      const touch = e.touches[0];
      const containerRect = containerRef.current.getBoundingClientRect();
      const containerWidth = containerRect.width;
      const deltaX = touch.clientX - startXRef.current;
      const deltaPercent = (deltaX / containerWidth) * 100;
      const newWidth = Math.min(
        maxLeftWidth,
        Math.max(minLeftWidth, startWidthRef.current + deltaPercent)
      );

      setLeftWidth(newWidth);
    },
    [isDragging, minLeftWidth, maxLeftWidth]
  );

  const handleMouseUp = useCallback(() => {
    if (isDragging) {
      setIsDragging(false);
      onResizeEnd?.(leftWidth);
    }
  }, [isDragging, leftWidth, onResizeEnd]);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      // Find the parent container (the element containing both panels)
      const resizer = e.currentTarget as HTMLElement;
      containerRef.current = resizer.parentElement;
      startXRef.current = e.clientX;
      startWidthRef.current = leftWidth;
      setIsDragging(true);
    },
    [leftWidth]
  );

  const handleTouchStart = useCallback(
    (e: React.TouchEvent) => {
      const touch = e.touches[0];
      const resizer = e.currentTarget as HTMLElement;
      containerRef.current = resizer.parentElement;
      startXRef.current = touch.clientX;
      startWidthRef.current = leftWidth;
      setIsDragging(true);
    },
    [leftWidth]
  );

  const reset = useCallback(() => {
    setLeftWidth(initialLeftWidth);
  }, [initialLeftWidth]);

  // Attach global mouse/touch events
  useEffect(() => {
    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.addEventListener('touchmove', handleTouchMove);
      document.addEventListener('touchend', handleMouseUp);

      // Prevent text selection while dragging
      document.body.style.userSelect = 'none';
      document.body.style.cursor = 'col-resize';
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.removeEventListener('touchmove', handleTouchMove);
      document.removeEventListener('touchend', handleMouseUp);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, [isDragging, handleMouseMove, handleMouseUp, handleTouchMove]);

  return {
    leftWidth,
    isDragging,
    resizerProps: {
      onMouseDown: handleMouseDown,
      onTouchStart: handleTouchStart,
    },
    reset,
  };
}
