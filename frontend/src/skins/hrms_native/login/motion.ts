import { useEffect } from 'react';
import Lenis from 'lenis';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import 'lenis/dist/lenis.css';

gsap.registerPlugin(ScrollTrigger);

export { usePrefersReducedMotion } from '../components/useReducedMotion';

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
