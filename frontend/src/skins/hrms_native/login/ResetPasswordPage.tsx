import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { CheckCircle, Eye, EyeOff, KeyRound } from 'lucide-react';
import { authApi } from '@/core/auth/api';
import PasswordRequirements, { isPasswordValid } from '@/core/components/PasswordRequirements';

function expiryHint(token: string): number | null {
  // Display hint only. Native authentication verifies signature, purpose, expiry
  // and password fingerprint before accepting any password change.
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return typeof payload.exp === 'number' && Number.isFinite(payload.exp) ? payload.exp * 1000 : null;
  } catch { return null; }
}

export default function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get('token') || '';
  // Reset all form state if another link is opened without unmounting this route.
  return <PasswordForm key={token} token={token} />;
}

function PasswordForm({ token }: { token: string }) {
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [visible, setVisible] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [unusable, setUnusable] = useState('');
  const [success, setSuccess] = useState(false);
  const [now, setNow] = useState(Date.now);
  const expiresAt = expiryHint(token);
  const expired = expiresAt !== null && expiresAt <= now;
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const linkError = !token ? 'This link is invalid' : expired ? 'This link has expired' : unusable;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (pending || linkError) return;
    setError('');
    if (!isPasswordValid(password)) {
      setError('Please meet the password requirements below.'); return;
    }
    if (password !== confirmation) { setError('Passwords do not match.'); return; }
    setPending(true);
    try {
      await authApi.resetPassword(token, password);
      setPassword(''); setConfirmation(''); setSuccess(true);
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : 'Could not update your password. Please retry.';
      if (/already been used/i.test(message)) setUnusable('This link has already been used');
      else if (/invalid or expired reset link/i.test(message)) setUnusable('This link is invalid or has expired');
      else setError(message);
    } finally { setPending(false); }
  }

  return <main className="max-w-lg mx-auto px-4 py-12">
    <section className="hrms-surface p-8 space-y-6">
      {success ? <>
        <CheckCircle className="text-emerald-600" size={32} aria-hidden="true" />
        <h1 className="text-3xl font-light">Password updated</h1>
        <p role="status">You can now sign in with your new password. This link can no longer be used.</p>
        <Link className="hrms-primary-button" to="/login">Sign in</Link>
      </> : <>
        <KeyRound className="text-[#0047AB]" size={32} aria-hidden="true" />
        <h1 className="text-3xl font-light">{linkError || 'Set your password'}</h1>
        {linkError ? <p role="alert">Request a new link using your work email. Your account approval and onboarding progress are unchanged.</p> : <>
          <p className="text-slate-600">Choose a password for your account. This email link is valid for one hour.</p>
          <form onSubmit={submit} className="space-y-5">
            {error && <p role="alert" className="text-red-700">{error}</p>}
            <div>
              <label className="block mb-2" htmlFor="new-password">New password</label>
              <div className="relative">
                <input id="new-password" type={visible ? 'text' : 'password'} autoComplete="new-password" required value={password} onChange={e => setPassword(e.target.value)} className="w-full rounded-xl border border-slate-200 p-3 pr-12" />
                <button type="button" aria-label={visible ? 'Hide password' : 'Show password'} className="absolute right-3 top-3" onClick={() => setVisible(!visible)}>{visible ? <EyeOff size={20} /> : <Eye size={20} />}</button>
              </div>
              <PasswordRequirements password={password} />
            </div>
            <div>
              <label className="block mb-2" htmlFor="confirm-password">Confirm password</label>
              <input id="confirm-password" type={visible ? 'text' : 'password'} autoComplete="new-password" required value={confirmation} onChange={e => setConfirmation(e.target.value)} className="w-full rounded-xl border border-slate-200 p-3" />
            </div>
            <button type="submit" disabled={pending} className="hrms-primary-button">{pending ? 'Saving…' : 'Save password'}</button>
          </form>
        </>}
        <div className="flex flex-wrap gap-4 items-center">
          <Link className={linkError ? 'hrms-primary-button' : 'hrms-text-link'} to="/forgot-password">Request a new link</Link>
          <Link className="hrms-text-link" to="/login">Back to sign in</Link>
        </div>
      </>}
    </section>
  </main>;
}
