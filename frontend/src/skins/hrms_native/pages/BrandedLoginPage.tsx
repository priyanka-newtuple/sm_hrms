import { InformationLinks } from '../components/Brand';
import { HrmsSignInForm } from '../login/HrmsSignInForm';
import { SpotlightCard } from '../login/reactbits';
import { Waves } from '../login/Waves';
import { Illustration } from '../components/Illustration';
import { usePrefersReducedMotion } from '../components/useReducedMotion';
import '../login/login.css';

/**
 * Single-screen login in the workspace's light theme over an animated line field (React Bits Waves):
 * published information on the left, the sign-in form on the right, nothing else.
 */
export default function BrandedLoginPage() {
  const motion = !usePrefersReducedMotion();

  return <main className={`hrms-login hrms-login-screen${motion ? ' hrms-login--motion' : ''}`}>
    <Waves animate={motion} className="hrms-login-waves" />
    <div className="hrms-login-panel">
      <span className="hrms-login-glow hrms-login-glow--a" aria-hidden="true" />
      <span className="hrms-login-glow hrms-login-glow--b" aria-hidden="true" />
      <span className="hrms-login-glow hrms-login-glow--c" aria-hidden="true" />
      <section className="hrms-login-info" aria-labelledby="hrms-discover-title">
        <div className="hrms-login-intro-row">
          <div>
            <h1 id="hrms-discover-title">Discover what’s happening</h1>
            <p className="hrms-login-tagline">Everything that connects us. All in one place.</p>
          </div>
          {/* "Hello" by LottieFiles creator suhayrasarwar — the same illustration family as the workspace. */}
          <div className="hrms-login-art"><Illustration name="login" animate={motion} /></div>
        </div>
        <InformationLinks />
      </section>

      <SpotlightCard className="hrms-login-card" spotlightColor="rgba(255, 255, 255, 0.55)" aria-label="Employee access">
        <HrmsSignInForm magnetic={motion} />
      </SpotlightCard>
    </div>
  </main>;
}
