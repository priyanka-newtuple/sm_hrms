import { useEffect, useRef, type ReactNode } from 'react';
import { createScope, createTimeline, stagger } from 'animejs';

/**
 * Word-by-word masked reveal (anime.js). Screen readers get the whole sentence from the
 * heading label; the split spans are presentation only.
 */
export function SplitHeadline({ lines, accent, animate, label }: { lines: string[]; accent?: ReactNode; animate: boolean; label: string }) {
  const root = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (!animate || !root.current) return;
    const hasAccent = Boolean(accent);
    const scope = createScope({ root }).add(() => {
      const timeline = createTimeline({ defaults: { ease: 'outExpo' } })
        .add('.hrms-split-word > span', { translateY: ['110%', '0%'], rotate: [6, 0], opacity: [0, 1], duration: 1300, delay: stagger(55) });
      if (hasAccent) timeline.add('.hrms-split-accent', { opacity: [0, 1], translateY: [24, 0], filter: ['blur(10px)', 'blur(0px)'], duration: 1200 }, '-=900');
    });
    return () => scope.revert();
  }, [animate, accent]);

  return <h1 ref={root} className="hrms-split-headline" aria-label={label}>
    {lines.map((line, lineIndex) => <span key={lineIndex} className="hrms-split-line" aria-hidden="true">
      {line.split(' ').map((word, wordIndex) => <span key={wordIndex} className="hrms-split-word"><span>{word}</span></span>)}
    </span>)}
    {accent && <span className="hrms-split-accent" aria-hidden="true">{accent}</span>}
  </h1>;
}
