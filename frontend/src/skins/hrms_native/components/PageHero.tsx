import type { ReactNode } from 'react';
import { usePrefersReducedMotion } from './useReducedMotion';
import { Illustration, type IllustrationName } from './Illustration';

export interface HeroStat { label: string; value: ReactNode; tone?: 'default' | 'attention' | 'positive' }

/**
 * Shared page header for signed-in HRMS screens: eyebrow, title, intro, the page's own actions,
 * an optional stats strip computed by the page from data it already loads, and its illustration.
 */
export function PageHero({ eyebrow, title, intro, illustration, actions, stats, compact = false }: {
  eyebrow: string; title: string; intro: string; illustration: IllustrationName; actions?: ReactNode; stats?: HeroStat[]; compact?: boolean;
}) {
  const motion = !usePrefersReducedMotion();
  return <header className={`hrms-page-hero${compact ? ' hrms-page-hero--compact' : ''}`}>
    <div className="hrms-page-hero-copy">
      <p className="hrms-page-eyebrow"><i aria-hidden="true" />{eyebrow}</p>
      <h1>{title}</h1>
      <p className="hrms-page-intro">{intro}</p>
      {actions && <div className="hrms-page-actions">{actions}</div>}
      {stats && stats.length > 0 && <dl className="hrms-page-stats">
        {stats.map(stat => <div key={stat.label} data-tone={stat.tone ?? 'default'}><dt>{stat.label}</dt><dd>{stat.value}</dd></div>)}
      </dl>}
    </div>
    <div className="hrms-page-hero-art"><Illustration name={illustration} animate={motion} /></div>
  </header>;
}
