import { useEffect, useRef } from 'react';
import { animate } from 'animejs';
import { AnimIcon, ArrowUpRightIcon } from '../animated-icons';

/*
 * Small closing band with public facts from newtuple.com/about-us and /life-at-newtuple.
 * Keep these in sync with the website. Numbers count up once when the band scrolls into view.
 */
const FACTS = [
  { value: 2022, prefix: '', suffix: '', label: 'Founded in Pune' },
  { value: 20, prefix: '', suffix: '+', label: 'GenAI deployments shipped' },
  { value: null, text: 'Hybrid', label: 'Remote culture built on trust' },
];

export function LifeAtNewtuple({ animate: shouldAnimate }: { animate: boolean }) {
  const root = useRef<HTMLElement>(null);

  useEffect(() => {
    const node = root.current;
    if (!shouldAnimate || !node) return;
    const counters = Array.from(node.querySelectorAll<HTMLElement>('[data-count]'));
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      observer.disconnect();
      counters.forEach(counter => {
        const target = Number(counter.dataset.count);
        const from = target > 1000 ? target - 12 : 0;
        const state = { n: from };
        animate(state, { n: target, duration: 1600, ease: 'outExpo', onUpdate: () => { counter.textContent = String(Math.round(state.n)); } });
      });
    }, { threshold: 0.4 });
    observer.observe(node);
    return () => observer.disconnect();
  }, [shouldAnimate]);

  return <section ref={root} className="hrms-life" aria-labelledby="hrms-life-title">
    <div className="hrms-life-quote">
      <p className="hrms-index-label">Life at Newtuple</p>
      <h2 id="hrms-life-title">Builders, dreamers and <em>problem-solvers.</em></h2>
      <a href="https://www.newtuple.com/life-at-newtuple" target="_blank" rel="noopener noreferrer" className="hrms-life-link">Life at Newtuple<AnimIcon icon={ArrowUpRightIcon} size={15} /><span className="sr-only"> (opens in a new tab)</span></a>
    </div>
    <dl className="hrms-life-facts">
      {FACTS.map(fact => <div key={fact.label}>
        <dt>{fact.label}</dt>
        <dd>{fact.value === null ? fact.text : <>{fact.prefix}<span data-count={fact.value}>{fact.value}</span>{fact.suffix}</>}</dd>
      </div>)}
    </dl>
  </section>;
}
