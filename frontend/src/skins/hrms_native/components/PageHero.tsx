import type { ReactNode } from 'react';
import { usePrefersReducedMotion } from './useReducedMotion';
import { Illustration, type IllustrationName } from './Illustration';

export interface HeroStat { label: string; value: ReactNode; tone?: 'default' | 'attention' | 'positive' }

/**
 * Compact page header for signed-in HRMS screens: title, intro and the page's own actions, a strip of
 * small stat boxes computed from data the page already loads, and an illustration. `tabs` places a
 * view switcher inside the header so it stays put when the view changes. Kept short so
 * the page's real content starts high on the screen.
 */
export function PageHero({ title, intro, illustration, actions, stats, tabs, compact = false }: {
  title: string; intro: string; illustration: IllustrationName; actions?: ReactNode; stats?: HeroStat[]; tabs?: ReactNode; compact?: boolean;
}) {
  const motion = !usePrefersReducedMotion();
  return <header className={`hrms-page-hero${compact ? ' hrms-page-hero--compact' : ''}`}>
    <div className="hrms-page-hero-copy">
      <h1>{title}</h1>
      <p className="hrms-page-intro">{intro}</p>
      {tabs && <div className="hrms-page-tabs">{tabs}</div>}
      {actions && <div className="hrms-page-actions">{actions}</div>}
    </div>
    {stats && stats.length > 0 && <dl className="hrms-page-stats">
      {stats.map(stat => <div key={stat.label} data-tone={stat.tone ?? 'default'}><dt>{stat.label}</dt><dd>{stat.value}</dd></div>)}
    </dl>}
    <div className="hrms-page-hero-art"><Illustration name={illustration} animate={motion} /></div>
  </header>;
}
