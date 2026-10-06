import { useEffect, useRef } from 'react';

/**
 * One illustration family for every HRMS screen: free LottieFiles animations by the creator
 * "suhayrasarwar" (lottiefiles.com/suhayrasarwar), self-hosted in public/hrms-brand/illustrations.
 * Add new scenes from the same creator only, so the visual style stays consistent.
 */
export type IllustrationName =
  | 'my-work' | 'leave' | 'performance' | 'employees' | 'onboarding' | 'projects'
  | 'allocations' | 'cockpit' | 'workflows' | 'settings' | 'all-clear';

const cache = new Map<IllustrationName, Promise<unknown>>();
const load = (name: IllustrationName) => {
  if (!cache.has(name)) cache.set(name, fetch(`/hrms-brand/illustrations/${name}.json`).then(r => (r.ok ? r.json() : Promise.reject(new Error(r.statusText)))));
  return cache.get(name)!;
};

/**
 * Decorative Lottie scene. The light SVG player loads lazily, plays only while visible and,
 * when `animate` is false (reduced motion), shows a single representative frame.
 */
export function Illustration({ name, animate = true, className = '' }: { name: IllustrationName; animate?: boolean; className?: string }) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = host.current;
    if (!node) return;
    let cancelled = false;
    let observer: IntersectionObserver | undefined;
    let player: { play(): void; pause(): void; destroy(): void; goToAndStop(value: number, isFrame?: boolean): void; totalFrames: number; addEventListener(name: string, cb: () => void): void } | undefined;

    Promise.all([import('lottie-web/build/player/lottie_light'), load(name)]).then(([module, data]) => {
      if (cancelled) return;
      player = module.default.loadAnimation({
        container: node, renderer: 'svg', loop: true, autoplay: false, animationData: data,
        rendererSettings: { preserveAspectRatio: 'xMidYMid meet', progressiveLoad: true },
      });
      if (!animate) {
        player.addEventListener('DOMLoaded', () => player?.goToAndStop(Math.floor(player.totalFrames * 0.55), true));
        return;
      }
      observer = new IntersectionObserver(([entry]) => (entry.isIntersecting ? player?.play() : player?.pause()));
      observer.observe(node);
    }).catch(() => { /* Decorative only: a failed load leaves the space empty. */ });

    return () => { cancelled = true; observer?.disconnect(); player?.destroy(); };
  }, [name, animate]);

  return <div ref={host} className={`hrms-illustration ${className}`} aria-hidden="true" />;
}
