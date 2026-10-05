import { useEffect, useRef, useState } from 'react';
import { AnimIcon, HammerIcon, HandHeartIcon, RocketIcon, ZapIcon, type AnimatedIcon } from '../animated-icons';

/**
 * "Our culture DNA": Newtuple's published values (newtuple.com/life-at-newtuple) riding a live
 * double helix. Transparent, brand-coloured, decorative geometry with real, focusable value text.
 */
const VALUES: Array<{ icon: AnimatedIcon; name: string; quote: string }> = [
  { icon: HandHeartIcon, name: 'Customer obsession', quote: 'Our clients never wait. When something needs attention, we’re on it.' },
  { icon: RocketIcon, name: 'Learn by doing', quote: 'We build with limited information rather than searching for the optimal solution.' },
  { icon: HammerIcon, name: 'Own your craft', quote: 'AI-assisted is not AI-replaced. Know the foundations of your role.' },
  { icon: ZapIcon, name: 'Speed as a habit', quote: 'If a task takes two days, we ask why it can’t be done in one.' },
];

const W = 600, H = 260, CY = 130, AMP = 62, K = (Math.PI * 2) / 280, X0 = 24, X1 = 576;
const NODE_X = [96, 236, 376, 516];
const RUNGS = Array.from({ length: Math.floor((X1 - X0) / 16) + 1 }, (_, i) => X0 + i * 16);
const CYCLE_MS = 3600;

function strand(phase: number, sign: 1 | -1) {
  let d = '';
  for (let x = X0; x <= X1; x += 6) d += `${x === X0 ? 'M' : 'L'}${x} ${(CY + sign * AMP * Math.sin(K * x + phase)).toFixed(1)}`;
  return d;
}

export function CultureDNA({ animate }: { animate: boolean }) {
  const root = useRef<HTMLDivElement>(null);
  const strandA = useRef<SVGPathElement>(null);
  const strandB = useRef<SVGPathElement>(null);
  const rungs = useRef<Array<SVGLineElement | null>>([]);
  const nodes = useRef<Array<SVGGElement | null>>([]);
  const stems = useRef<Array<SVGLineElement | null>>([]);
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);

  // Draw the helix for a phase; called every frame when animating, once otherwise.
  const draw = (phase: number) => {
    strandA.current?.setAttribute('d', strand(phase, 1));
    strandB.current?.setAttribute('d', strand(phase, -1));
    RUNGS.forEach((x, i) => {
      const line = rungs.current[i];
      if (!line) return;
      const s = Math.sin(K * x + phase);
      line.setAttribute('y1', (CY + AMP * s).toFixed(1));
      line.setAttribute('y2', (CY - AMP * s).toFixed(1));
      line.setAttribute('stroke-opacity', (0.12 + 0.4 * Math.abs(Math.cos(K * x + phase))).toFixed(2));
    });
    NODE_X.forEach((x, i) => {
      const y = CY + AMP * Math.sin(K * x + phase);
      nodes.current[i]?.setAttribute('transform', `translate(${x} ${y.toFixed(1)})`);
      const stem = stems.current[i];
      if (stem) { stem.setAttribute('y1', y.toFixed(1)); }
    });
  };

  useEffect(() => {
    draw(0.6);
    if (!animate || !root.current) return;
    let frame = 0, phase = 0.6, last = performance.now(), visible = true;
    const observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; });
    observer.observe(root.current);
    const loop = (time: number) => {
      const dt = Math.min((time - last) / 1000, 0.05);
      last = time;
      if (visible) { phase += dt * 0.55; draw(phase); }
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    return () => { cancelAnimationFrame(frame); observer.disconnect(); };
  }, [animate]);

  useEffect(() => {
    if (!animate || paused) return;
    const timer = window.setInterval(() => setActive(index => (index + 1) % VALUES.length), CYCLE_MS);
    return () => window.clearInterval(timer);
  }, [animate, paused]);

  return <div ref={root} className="hrms-dna" onMouseLeave={() => setPaused(false)}>
    <p className="hrms-dna-label"><span aria-hidden="true" />Our culture DNA</p>
    <div className="hrms-dna-stage">
      <svg viewBox={`0 0 ${W} ${H}`} aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id="hrms-dna-a" x1="0" x2="1"><stop offset="0" stopColor="#6f9cf0" stopOpacity=".2" /><stop offset=".5" stopColor="#ffffff" /><stop offset="1" stopColor="#6f9cf0" stopOpacity=".2" /></linearGradient>
          <linearGradient id="hrms-dna-b" x1="0" x2="1"><stop offset="0" stopColor="#cfe0ff" stopOpacity=".05" /><stop offset=".5" stopColor="#8fb3f0" stopOpacity=".7" /><stop offset="1" stopColor="#cfe0ff" stopOpacity=".05" /></linearGradient>
          <filter id="hrms-dna-glow" x="-20%" y="-50%" width="140%" height="200%"><feGaussianBlur stdDeviation="3" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        </defs>
        {RUNGS.map((x, i) => <line key={x} ref={el => { rungs.current[i] = el; }} x1={x} x2={x} y1={CY} y2={CY} stroke="#cfe0ff" strokeWidth="1.2" strokeLinecap="round" />)}
        <path ref={strandB} fill="none" stroke="url(#hrms-dna-b)" strokeWidth="1.6" />
        <path ref={strandA} fill="none" stroke="url(#hrms-dna-a)" strokeWidth="2.6" filter="url(#hrms-dna-glow)" />
        {NODE_X.map((x, i) => <line key={`stem-${x}`} ref={el => { stems.current[i] = el; }} className="hrms-dna-stem" data-active={i === active} x1={x} x2={x} y1={CY} y2={i % 2 === 0 ? 14 : H - 14} />)}
        {NODE_X.map((x, i) => <g key={`node-${x}`} ref={el => { nodes.current[i] = el; }} className="hrms-dna-node" data-active={i === active}>
          <circle className="hrms-dna-pulse" r="16" />
          <circle r="7" />
        </g>)}
      </svg>
      <ul className="hrms-dna-values" aria-label="Newtuple values">
        {VALUES.map((value, i) => <li key={value.name} style={{ left: `${(NODE_X[i] / W) * 100}%` }} data-row={i % 2 === 0 ? 'top' : 'bottom'}>
          <button type="button" data-active={i === active} aria-pressed={i === active}
            onMouseEnter={() => { setActive(i); setPaused(true); }} onFocus={() => { setActive(i); setPaused(true); }} onBlur={() => setPaused(false)} onClick={() => setActive(i)}>
            <AnimIcon icon={value.icon} size={15} play={i === active} />{value.name}
            <span className="sr-only">: {value.quote}</span>
          </button>
        </li>)}
      </ul>
    </div>
    <p className="hrms-dna-quote" aria-hidden="true" key={active}><span>“{VALUES[active].quote}”</span></p>
  </div>;
}
