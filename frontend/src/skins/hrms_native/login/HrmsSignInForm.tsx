import { useId, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Building2 } from 'lucide-react';
import { AnimIcon, ArrowRightIcon, CheckIcon, EyeIcon, EyeOffIcon, LoaderCircleIcon } from '../animated-icons';
import { useAuth } from '../../../core/auth';
import { PendingApprovalError, RegistrationPendingError } from '../../../core/auth/api';
import { isPasswordValid } from '../../../core/components/PasswordRequirements';
import { Magnet } from './reactbits';

/**
 * HRMS presentation of the native sign-in/sign-up flow. Behaviour mirrors core
 * pages/auth/LoginPage.tsx (same auth calls, validation, pending-approval routing);
 * only the markup is product-owned. Re-check this file when the native page changes.
 */
type Mode = 'signin' | 'signup';

const PUBLIC_EMAIL_DOMAINS = new Set(['gmail.com', 'googlemail.com', 'outlook.com', 'hotmail.com', 'live.com', 'msn.com', 'yahoo.com', 'ymail.com', 'icloud.com', 'me.com', 'mac.com', 'aol.com', 'protonmail.com', 'proton.me', 'zoho.com', 'mail.com', 'gmx.com', 'fastmail.com']);
const SPECIAL_CHAR_RE = /[!@#$%^&*(),.?":{}|<>[\]\\;'`~\-_+=^]/;
const STRENGTH_LABELS = ['', 'Very weak', 'Weak', 'Fair', 'Good', 'Strong'];

function strengthScore(password: string) {
  return [password.length >= 8, password.length >= 12, SPECIAL_CHAR_RE.test(password), /[A-Z]/.test(password), /[0-9]/.test(password)].filter(Boolean).length;
}

function Field({ id, label, aside, children }: { id: string; label: string; aside?: ReactNode; children: ReactNode }) {
  return <div className="hrms-field">
    <div className="hrms-field-box">{children}<label htmlFor={id}>{label}</label><span className="hrms-field-line" aria-hidden="true" /></div>
    {aside}
  </div>;
}

function PasswordChecklist({ password }: { password: string }) {
  if (!password) return null;
  const rules = [
    { label: '8+ characters', met: password.length >= 8 },
    { label: 'Uppercase letter', met: /[A-Z]/.test(password) },
    { label: 'Special character', met: SPECIAL_CHAR_RE.test(password) },
  ];
  const score = strengthScore(password);
  return <div className="hrms-password-meter">
    <ul aria-label="Password requirements">
      {rules.map(rule => <li key={rule.label} data-met={rule.met} aria-label={`${rule.label}: ${rule.met ? 'met' : 'not met'}`}><AnimIcon icon={CheckIcon} size={13} play={rule.met} />{rule.label}</li>)}
    </ul>
    <div className="hrms-strength" aria-label={`Password strength: ${STRENGTH_LABELS[score]}`}>
      <div aria-hidden="true">{[1, 2, 3, 4, 5].map(step => <i key={step} data-on={step <= score} />)}</div>
      <span>{STRENGTH_LABELS[score]}</span>
    </div>
  </div>;
}

const GoogleIcon = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" /><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" /><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" /><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" /></svg>;
const MicrosoftIcon = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#F25022" d="M2 2h9.5v9.5H2z" /><path fill="#7FBA00" d="M12.5 2H22v9.5h-9.5z" /><path fill="#00A4EF" d="M2 12.5h9.5V22H2z" /><path fill="#FFB900" d="M12.5 12.5H22V22h-9.5z" /></svg>;

export function HrmsSignInForm({ magnetic }: { magnetic: boolean }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, register, loginWithGoogle, loginWithMicrosoft, isLoading: authLoading } = useAuth();
  const uid = useId();
  const [mode, setMode] = useState<Mode>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [orgName, setOrgName] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const from = (location.state as { from?: { pathname: string } } | null)?.from?.pathname || '/';
  const isPublicDomain = useMemo(() => PUBLIC_EMAIL_DOMAINS.has(email.split('@')[1]?.toLowerCase() ?? ''), [email]);
  const showOrgName = mode === 'signup' && isPublicDomain;
  const ids = { name: `${uid}-name`, email: `${uid}-email`, org: `${uid}-org`, password: `${uid}-password` };

  const switchMode = (next: Mode) => { setMode(next); setShowPassword(false); setError(''); };

  const routePending = (err: unknown) => {
    if (err instanceof PendingApprovalError) {
      navigate('/pending-approval', { state: { email, name: fullName || email.split('@')[0], approvalType: 'pending_org_admin' } });
      return true;
    }
    if (err instanceof RegistrationPendingError) {
      navigate('/pending-approval', { state: { email, name: fullName, orgName: err.organizationName, approvalType: err.approvalType, isNewOrg: err.isNewOrganization } });
      return true;
    }
    return false;
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    if (mode === 'signup') {
      if (!fullName.trim()) return setError('Please enter your full name');
      if (showOrgName && !orgName.trim()) return setError('Please enter an organization name');
      if (!isPasswordValid(password)) return setError('Password must be at least 8 characters and include an uppercase letter and a special character');
    }
    setSubmitting(true);
    try {
      if (mode === 'signup') await register(email, password, fullName, showOrgName ? orgName : undefined);
      else await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      if (!routePending(err)) setError(err instanceof Error ? err.message : 'Authentication failed');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSso = (provider: 'google' | 'microsoft') => async () => {
    setError('');
    try {
      await (provider === 'google' ? loginWithGoogle() : loginWithMicrosoft());
    } catch (err) {
      if (!routePending(err)) setError(err instanceof Error ? err.message : `${provider === 'google' ? 'Google' : 'Microsoft'} login failed`);
    }
  };

  if (authLoading) return <div className="hrms-form-loading" role="status"><AnimIcon icon={LoaderCircleIcon} className="hrms-spin" size={22} />Checking your session…</div>;

  const submitLabel = mode === 'signin' ? 'Sign in' : showOrgName ? 'Request organization' : 'Create account';
  const submit = <button type="submit" className="hrms-submit" disabled={submitting}>
    <span>{submitting ? (mode === 'signin' ? 'Signing in…' : 'Creating account…') : submitLabel}</span>
    <i aria-hidden="true">{submitting ? <AnimIcon icon={LoaderCircleIcon} className="hrms-spin" size={18} /> : <AnimIcon icon={ArrowRightIcon} size={18} />}</i>
  </button>;

  return <div className="hrms-signin-form" data-mode={mode}>
    <header className="hrms-signin-head">
      <p className="hrms-index-label">Employee access</p>
      <h2>{mode === 'signin' ? 'Welcome back' : 'Join your workspace'}</h2>
      <p>{mode === 'signin' ? 'Sign in to your Newtuple workspace.' : 'Create your account with your work email.'}</p>
    </header>
    <div className="hrms-mode-switch" role="group" aria-label="Account access">
      <span className="hrms-mode-indicator" aria-hidden="true" />
      <button type="button" aria-pressed={mode === 'signin'} onClick={() => switchMode('signin')}>Sign in</button>
      <button type="button" aria-pressed={mode === 'signup'} onClick={() => switchMode('signup')}>Create account</button>
    </div>

    <form onSubmit={handleSubmit}>
      <div aria-live="assertive">{error && <p className="hrms-form-error" role="alert">{error}</p>}</div>

      {mode === 'signup' && <div className="hrms-field-enter">
        <Field id={ids.name} label="Full name"><input id={ids.name} name="fullName" type="text" autoComplete="name" required placeholder=" " value={fullName} onChange={e => setFullName(e.target.value)} /></Field>
      </div>}

      <Field id={ids.email} label="Work email"><input id={ids.email} name="email" type="email" autoComplete="email" required placeholder=" " value={email} onChange={e => setEmail(e.target.value)} /></Field>

      {showOrgName && <div className="hrms-field-enter">
        <p className="hrms-org-notice"><Building2 size={16} aria-hidden="true" />Personal email detected. Add your organization name to request a new workspace — a platform administrator reviews it.</p>
        <Field id={ids.org} label="Organization name"><input id={ids.org} name="orgName" type="text" required placeholder=" " value={orgName} onChange={e => setOrgName(e.target.value)} /></Field>
      </div>}

      <Field id={ids.password} label={mode === 'signin' ? 'Password' : 'Create a password'} aside={mode === 'signup' ? <PasswordChecklist password={password} /> : undefined}>
        <input id={ids.password} name="password" type={showPassword ? 'text' : 'password'} autoComplete={mode === 'signin' ? 'current-password' : 'new-password'} required placeholder=" " value={password} onChange={e => setPassword(e.target.value)} />
        <button type="button" className="hrms-reveal" onClick={() => setShowPassword(value => !value)} aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword}><AnimIcon key={showPassword ? 'hide' : 'show'} icon={showPassword ? EyeOffIcon : EyeIcon} size={17} /></button>
      </Field>

      {mode === 'signin' && <Link to="/forgot-password" className="hrms-forgot">Forgot password?</Link>}

      {magnetic ? <Magnet strength={10}>{submit}</Magnet> : submit}
    </form>

    <p className="hrms-or"><span>or continue with</span></p>
    <div className="hrms-sso">
      <button type="button" onClick={handleSso('google')} aria-label={`${mode === 'signin' ? 'Sign in' : 'Sign up'} with Google`}><GoogleIcon />Google</button>
      <button type="button" onClick={handleSso('microsoft')} aria-label={`${mode === 'signin' ? 'Sign in' : 'Sign up'} with Microsoft`}><MicrosoftIcon />Microsoft</button>
    </div>
  </div>;
}
