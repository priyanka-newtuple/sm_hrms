import { lazy } from 'react';
import { InformationLinks } from '../components/Brand';

const NativeLoginPage = lazy(() => import('../../../pages/auth/LoginPage'));

export default function BrandedLoginPage() {
  return <main className="hrms-login-layout">
    <section className="hrms-welcome" aria-labelledby="hrms-discover-title">
      <h1 id="hrms-discover-title">Discover what’s happening</h1>
      <p className="hrms-welcome-tagline">Everything that connects us. All in one place.</p>
      <InformationLinks />
    </section>
    <section className="hrms-signin" aria-label="Employee access"><p className="hrms-eyebrow">EMPLOYEE ACCESS</p><h2>Welcome back</h2><p>Sign in to your Newtuple workspace.</p>
      {/* Keep native authentication intact. The scoped adapter only replaces its branding and outer layout. */}
      <div className="hrms-auth-form"><NativeLoginPage /></div>
    </section>
  </main>;
}
