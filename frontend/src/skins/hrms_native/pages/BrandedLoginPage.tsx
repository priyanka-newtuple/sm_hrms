import { ExternalLink } from 'lucide-react';
import { InformationLinks, externalResources } from '../components/Brand';
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
        <p className="hrms-login-tagline">Everything that connects us. All in one place.</p>
        <InformationLinks includeExternal={false} />
        <nav className="hrms-login-tools" aria-label="More Newtuple tools">
          {externalResources.map(({ id, title, href }) => <a key={id} href={href} target="_blank" rel="noopener noreferrer">
            {title}<ExternalLink size={14} aria-hidden="true" /><span className="sr-only"> (opens in a new tab)</span>
          </a>)}
        </nav>
      </section>
      <section className="hrms-login-card" aria-label="Employee access">
        <HrmsSignInForm magnetic={false} />
      </section>
    </div>
  </main>;
}
