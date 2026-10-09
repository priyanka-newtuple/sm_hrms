import { useId, useState, type FormEvent, type ReactNode } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { AnimIcon, ArrowRightIcon, EyeIcon, EyeOffIcon, LoaderCircleIcon } from '../animated-icons';
import { useAuth } from '../../../core/auth';
import { PendingApprovalError, RegistrationPendingError } from '../../../core/auth/api';
import { MyHubWordmark } from '../components/MyHubWordmark';
import { Magnet } from './reactbits';

/** HRMS sign-in presentation; employee accounts are provisioned by administrators. */
function Field({ id, label, aside, children }: { id: string; label: string; aside?: ReactNode; children: ReactNode }) {
  return <div className="hrms-field">
    <div className="hrms-field-box">{children}<label htmlFor={id}>{label}</label><span className="hrms-field-line" aria-hidden="true" /></div>
    {aside}
  </div>;
}

const GoogleIcon = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" /><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" /><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" /><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" /></svg>;

export function HrmsSignInForm({ magnetic }: { magnetic: boolean }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, loginWithGoogle, isLoading: authLoading } = useAuth();
  const uid = useId();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const from = (location.state as { from?: { pathname: string } } | null)?.from?.pathname || '/';
  const ids = { email: `${uid}-email`, password: `${uid}-password` };


  const routePending = (err: unknown) => {
    if (err instanceof PendingApprovalError) {
      navigate('/pending-approval', { state: { email, name: email.split('@')[0], approvalType: 'pending_org_admin' } });
      return true;
    }
    if (err instanceof RegistrationPendingError) {
      navigate('/pending-approval', { state: { email, name: email.split('@')[0], orgName: err.organizationName, approvalType: err.approvalType, isNewOrg: err.isNewOrganization } });
      return true;
    }
    return false;
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      if (!routePending(err)) setError(err instanceof Error ? err.message : 'Authentication failed');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSso = async () => {
    setError('');
    try {
      await loginWithGoogle();
    } catch (err) {
      if (!routePending(err)) setError(err instanceof Error ? err.message : 'Google login failed');
    }
  };

  if (authLoading) return <div className="hrms-form-loading" role="status"><AnimIcon icon={LoaderCircleIcon} className="hrms-spin" size={22} />Checking your session…</div>;

  const submit = <button type="submit" className="hrms-submit" disabled={submitting}>
    <span>{submitting ? 'Signing in...' : 'Sign in'}</span>
    <i aria-hidden="true">{submitting ? <AnimIcon icon={LoaderCircleIcon} className="hrms-spin" size={18} /> : <AnimIcon icon={ArrowRightIcon} size={18} />}</i>
  </button>;

  return <div className="hrms-signin-form" data-mode="signin">
    <header className="hrms-signin-head">
      <p className="hrms-index-label">Employee access</p>
      <h2 className="hrms-myhub-title"><MyHubWordmark /></h2>
      <p>Sign in to your Newtuple workspace.</p>
    </header>
    <form onSubmit={handleSubmit}>
      <div aria-live="assertive">{error && <p className="hrms-form-error" role="alert">{error}</p>}</div>

      <Field id={ids.email} label="Work email"><input id={ids.email} name="email" type="email" autoComplete="email" required placeholder=" " value={email} onChange={e => setEmail(e.target.value)} /></Field>

      <Field id={ids.password} label="Password">
        <input id={ids.password} name="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" required placeholder=" " value={password} onChange={e => setPassword(e.target.value)} />
        <button type="button" className="hrms-reveal" onClick={() => setShowPassword(value => !value)} aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword}><AnimIcon key={showPassword ? 'hide' : 'show'} icon={showPassword ? EyeOffIcon : EyeIcon} size={17} /></button>
      </Field>

      <Link to="/forgot-password" className="hrms-forgot">Forgot password?</Link>

      {magnetic ? <Magnet strength={10}>{submit}</Magnet> : submit}
    </form>

    <p className="hrms-or"><span>or continue with</span></p>
    <div className="hrms-sso">
      <button type="button" onClick={handleSso} aria-label="Sign in with Google"><GoogleIcon />Continue with Google</button>
    </div>
    <p className="hrms-google-help">Use your @newtuple.com Google Workspace account.</p>
    <p className="hrms-google-help">Need access? Contact your HR administrator for an invitation.</p>
  </div>;
}
