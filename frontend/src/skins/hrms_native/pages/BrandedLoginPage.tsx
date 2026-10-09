import { SocialDiscovery } from '../components/SocialDiscovery';
import { HrmsSignInForm } from '../login/HrmsSignInForm';
import '../login/login.css';

/** Approved office composition; authentication and the original brand header are reused. */
export default function BrandedLoginPage() {
  return <main className="hrms-login hrms-login-screen">
    <div className="hrms-login-panel">
      <div className="hrms-login-photo" aria-hidden="true">
        <img src="/hrms-brand/login/office-happen.png" alt="" decoding="async" fetchPriority="high" />
      </div>
      <section className="hrms-login-info" aria-labelledby="hrms-discover-title">
        <h1 id="hrms-discover-title">Discover what’s happening</h1>
        <p className="hrms-login-tagline">Ideas, stories and life at Newtuple. Stay connected.</p>
        <SocialDiscovery />
      </section>
      <section className="hrms-login-card" aria-label="Employee access">
        <HrmsSignInForm magnetic={false} />
      </section>
    </div>
  </main>;
}
