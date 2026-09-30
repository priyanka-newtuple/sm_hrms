import { lazy } from 'react';
import { InformationLinks } from '../components/Brand';

const NativeLoginPage = lazy(() => import('../../../pages/auth/LoginPage'));

export default function BrandedLoginPage() {
  return <main className="hrms-login-layout">
    <section className="hrms-welcome"><p className="hrms-eyebrow">WELCOME TO NEWTUPLE</p><h1>A place for people.<br /><span>Room to grow.</span></h1><p className="hrms-intro">Your work, your development, and everything that connects us. All in one place.</p><div className="hrms-explore-heading"><h2>Discover what’s happening</h2><span>No sign-in needed</span></div><InformationLinks /></section>
    <section className="hrms-signin" aria-label="Employee access"><p className="hrms-eyebrow">EMPLOYEE ACCESS</p><h2>Welcome back</h2><p>Sign in to your Newtuple workspace.</p>
      {/* Keep native authentication intact. The scoped adapter only replaces its branding and outer layout. */}
      <div className="hrms-auth-form"><NativeLoginPage /></div>
    </section>
  </main>;
}
