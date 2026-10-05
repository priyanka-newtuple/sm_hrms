import { useRef } from 'react';
import { Link } from 'react-router-dom';
import * as Scrollytelling from '@bsmnt/scrollytelling';
import { AnimIcon, ArrowDownIcon, ArrowRightIcon } from '../animated-icons';
import { InformationLinks } from '../components/Brand';
import { HeroBackdrop } from '../login/HeroBackdrop';
import { CultureDNA } from '../login/CultureDNA';
import { SplitHeadline } from '../login/SplitHeadline';
import { HrmsSignInForm } from '../login/HrmsSignInForm';
import { LocalTime } from '../login/LocalTime';
import { ShinyText, SpotlightCard } from '../login/reactbits';
import { LifeAtNewtuple } from '../login/LifeAtNewtuple';
import { usePrefersReducedMotion, useRevealOnEnter, useSmoothScroll } from '../login/motion';
import '../login/login.css';


export default function BrandedLoginPage() {
  const reducedMotion = usePrefersReducedMotion();
  const motion = !reducedMotion;
  useSmoothScroll(motion);
  const discover = useRef<HTMLElement>(null);
  useRevealOnEnter(discover, '.hrms-discover-aside > *, .hrms-resource-card', motion);

  return <main className={`hrms-login${motion ? ' hrms-login--motion' : ''}`}>
    <Scrollytelling.Root start="top top" end="bottom top" scrub disabled={!motion}>
      <section className="hrms-login-hero">
        <Scrollytelling.Animation tween={{ target: '.hrms-login-backdrop', start: 0, end: 100, to: { scale: 1.12, yPercent: 8, ease: 'none' } }} />
        <Scrollytelling.Animation tween={[
          { target: '.hrms-login-story', start: 0, end: 100, to: { y: -90, opacity: 0.25, ease: 'none' } },
          { target: '.hrms-dna', start: 0, end: 100, to: { y: -50, ease: 'none' } },
          { target: '.hrms-login-card', start: 0, end: 100, to: { y: -40, ease: 'none' } },
        ]} />
        <HeroBackdrop animate={motion} />

        <div className="hrms-login-hero-inner">
          <div className="hrms-login-story">
            <div className="hrms-login-meta">
              <p className="hrms-login-chip"><i aria-hidden="true" />Welcome to Newtuple</p>
              <LocalTime />
            </div>
            <SplitHeadline
              label="Everything that connects us. All in one place."
              lines={['Everything that', 'connects us.']}
              accent={<ShinyText text="All in one place." disabled={!motion} />}
              animate={motion}
            />
            <p className="hrms-login-intro">Your work, your development, and everything that connects us — leave, projects, performance and onboarding in one workspace.</p>
            <CultureDNA animate={motion} />
          </div>

          <SpotlightCard className="hrms-login-card" spotlightColor="rgba(255, 255, 255, 0.16)" aria-label="Employee access">
            <HrmsSignInForm magnetic={motion} />
          </SpotlightCard>
        </div>

        <a className="hrms-login-scroll" href="#discover"><span>Scroll to discover</span><AnimIcon icon={ArrowDownIcon} size={15} every={motion ? 3000 : undefined} /></a>
      </section>
    </Scrollytelling.Root>

    <section ref={discover} id="discover" className="hrms-login-discover" aria-labelledby="hrms-discover-title">
      <div className="hrms-discover-aside">
        <p className="hrms-index-label">Open to everyone</p>
        <h2 id="hrms-discover-title">Discover what’s happening</h2>
        <p>Policies, learning, holidays and careers — published by HR and readable without signing in.</p>
        <Link to="/public" className="hrms-discover-link">Browse everything<AnimIcon icon={ArrowRightIcon} size={16} /></Link>
      </div>
      <InformationLinks />
    </section>

    <LifeAtNewtuple animate={motion} />
  </main>;
}
