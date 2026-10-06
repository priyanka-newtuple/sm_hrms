import { useState } from 'react';

export interface DonutSlice { label: string; count: number }

const COLORS = ['#0047ab', '#5b8def', '#9dbcf3', '#0a1f4d', '#2f6fd6'];
const R = 42, C = 2 * Math.PI * R;

/**
 * Interactive donut for the My Work summary: one slice per work area the user can act on.
 * Hovering or focusing a legend row highlights its slice; the centre shows that slice's count.
 */
export function ActionDonut({ slices }: { slices: DonutSlice[] }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const total = slices.reduce((sum, slice) => sum + slice.count, 0);
  let offset = 0;
  const focus = hovered !== null ? slices[hovered] : null;

  return <div className="hrms-donut">
    <svg viewBox="0 0 100 100" aria-hidden="true" focusable="false">
      <circle cx="50" cy="50" r={R} className="hrms-donut-track" />
      {total > 0 && slices.map((slice, index) => {
        const length = (slice.count / total) * C;
        const element = slice.count > 0 && <circle key={slice.label} cx="50" cy="50" r={R} className="hrms-donut-slice"
          data-dim={hovered !== null && hovered !== index} stroke={COLORS[index % COLORS.length]}
          strokeDasharray={`${Math.max(length - 1.5, 0.01)} ${C}`} strokeDashoffset={-offset} />;
        offset += length;
        return element;
      })}
      <text x="50" y="48" className="hrms-donut-value">{focus ? focus.count : total}</text>
      <text x="50" y="62" className="hrms-donut-caption">{focus ? focus.label : total === 1 ? 'action' : 'actions'}</text>
    </svg>
    <ul className="hrms-donut-legend">
      {slices.map((slice, index) => <li key={slice.label} tabIndex={0} data-active={slice.count > 0}
        onMouseEnter={() => setHovered(index)} onMouseLeave={() => setHovered(null)} onFocus={() => setHovered(index)} onBlur={() => setHovered(null)}
        aria-label={`${slice.label}: ${slice.count}`}>
        <i style={{ background: COLORS[index % COLORS.length] }} aria-hidden="true" /><span>{slice.label}</span><b>{slice.count}</b>
      </li>)}
    </ul>
  </div>;
}
