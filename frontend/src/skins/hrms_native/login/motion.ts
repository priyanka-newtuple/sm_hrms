import { useEffect, useState } from 'react';
import Lenis from 'lenis';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import 'lenis/dist/lenis.css';

gsap.registerPlugin(ScrollTrigger);

const REDUCED_MOTION = '(prefers-reduced-motion: reduce)';

/** Tracks the operating-system reduced-motion preference so every effect can opt out together. */
export function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(() => typeof window !== 'undefined' && window.matchMedia(REDUCED_MOTION).matches);
  useEffect(() => {
    const query = window.matchMedia(REDUCED_MOTION);
    const update = () => setReduced(query.matches);
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);
  return reduced;
}

/**
 * One-shot staggered reveal when a section enters the viewport. Unlike a scrubbed timeline it
 * always completes, even on screens too tall to scroll the section to its end position.
 */
export function useRevealOnEnter(root: React.RefObject<HTMLElement | null>, selector: string, enabled: boolean) {
  useEffect(() => {
    if (!enabled || !root.current) return;
    const context = gsap.context(() => {
      gsap.from(selector, {
        opacity: 0, y: 64, rotateX: -12, duration: 1.1, ease: 'power3.out', stagger: 0.1,
        scrollTrigger: { trigger: root.current, start: 'top 82%', once: true },
      });
    }, root);
    return () => context.revert();
  }, [root, selector, enabled]);
}

/**
 * Lenis smooth scrolling for the public login page only. Lenis is driven by the GSAP ticker
 * and reports each frame to ScrollTrigger, so the Scrollytelling timelines stay in sync.
 */
export function useSmoothScroll(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
    const lenis = new Lenis({ autoRaf: false, lerp: 0.09, anchors: true });
    const unsubscribe = lenis.on('scroll', ScrollTrigger.update);
    const tick = (time: number) => lenis.raf(time * 1000);
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);
    return () => {
      gsap.ticker.remove(tick);
      gsap.ticker.lagSmoothing(500, 33);
      unsubscribe();
      lenis.destroy();
    };
  }, [enabled]);
}
