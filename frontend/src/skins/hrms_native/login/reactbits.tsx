/**
 * Adapted from React Bits (https://reactbits.dev, MIT + Commons Clause): ShinyText, SpotlightCard
 * and Magnet. ShinyText uses the CSS-only variant so the page needs no extra animation runtime.
 * Colors are bound to the HRMS cobalt palette; styles live in login.css.
 */
import { useEffect, useRef, type CSSProperties, type MouseEventHandler, type ReactNode } from 'react';

/** Pulls its child toward the pointer while the pointer is nearby. */
export function Magnet({ children, strength = 14, padding = 60 }: { children: ReactNode; strength?: number; padding?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const move = (event: PointerEvent) => {
      const rect = node.getBoundingClientRect();
      const dx = event.clientX - (rect.left + rect.width / 2);
      const dy = event.clientY - (rect.top + rect.height / 2);
      const near = Math.abs(dx) < rect.width / 2 + padding && Math.abs(dy) < rect.height / 2 + padding;
      node.style.transform = near ? `translate3d(${dx / strength}px, ${dy / strength}px, 0)` : '';
    };
    const reset = () => { node.style.transform = ''; };
    window.addEventListener('pointermove', move);
    document.addEventListener('pointerleave', reset);
    return () => { window.removeEventListener('pointermove', move); document.removeEventListener('pointerleave', reset); };
  }, [strength, padding]);
  return <div ref={ref} className="rb-magnet">{children}</div>;
}

export function ShinyText({ text, speed = 5, disabled = false, className = '' }: { text: string; speed?: number; disabled?: boolean; className?: string }) {
  return <span className={`rb-shiny-text${disabled ? ' rb-shiny-text--disabled' : ''} ${className}`} style={{ '--rb-shine-duration': `${speed}s` } as CSSProperties}>{text}</span>;
}

export function SpotlightCard({ children, className = '', spotlightColor = 'rgba(0, 71, 171, 0.14)', ...rest }: { children: ReactNode; className?: string; spotlightColor?: string } & Omit<React.HTMLAttributes<HTMLElement>, 'className' | 'children'>) {
  const ref = useRef<HTMLElement>(null);
  const handleMouseMove: MouseEventHandler<HTMLElement> = event => {
    const node = ref.current;
    if (!node) return;
    const rect = node.getBoundingClientRect();
    node.style.setProperty('--mouse-x', `${event.clientX - rect.left}px`);
    node.style.setProperty('--mouse-y', `${event.clientY - rect.top}px`);
  };
  return <section ref={ref} onMouseMove={handleMouseMove} className={`rb-spotlight ${className}`} style={{ '--spotlight-color': spotlightColor } as CSSProperties} {...rest}>{children}</section>;
}
