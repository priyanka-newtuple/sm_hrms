import { useEffect, useRef, type ForwardRefExoticComponent, type HTMLAttributes, type RefAttributes } from 'react';

export interface AnimatedIconHandle {
  startAnimation: () => void;
  stopAnimation: () => void;
}
export type AnimatedIcon = ForwardRefExoticComponent<HTMLAttributes<HTMLDivElement> & { size?: number } & RefAttributes<AnimatedIconHandle>>;

/**
 * Renders a lucide-animated icon and plays it when its nearest link/button is hovered or focused,
 * so the whole control — not just the glyph — triggers the motion. `play` drives it from state
 * (e.g. a rule becoming met); `every` replays it on a timer for decorative, non-interactive use.
 */
export function AnimIcon({ icon: Icon, size = 18, className = '', play, every }: { icon: AnimatedIcon; size?: number; className?: string; play?: boolean; every?: number }) {
  const handle = useRef<AnimatedIconHandle>(null);
  const host = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const target = host.current?.closest<HTMLElement>('a, button, [data-anim-trigger]');
    if (!target) return;
    const start = () => handle.current?.startAnimation();
    const stop = () => handle.current?.stopAnimation();
    target.addEventListener('mouseenter', start);
    target.addEventListener('mouseleave', stop);
    target.addEventListener('focusin', start);
    target.addEventListener('focusout', stop);
    return () => {
      target.removeEventListener('mouseenter', start);
      target.removeEventListener('mouseleave', stop);
      target.removeEventListener('focusin', start);
      target.removeEventListener('focusout', stop);
    };
  }, []);

  useEffect(() => {
    if (play === undefined) return;
    if (play) handle.current?.startAnimation(); else handle.current?.stopAnimation();
  }, [play]);

  useEffect(() => {
    if (!every) return;
    const timer = window.setInterval(() => handle.current?.startAnimation(), every);
    return () => window.clearInterval(timer);
  }, [every]);

  return <span ref={host} className={`hrms-anim-icon ${className}`} aria-hidden="true"><Icon ref={handle} size={size} /></span>;
}
