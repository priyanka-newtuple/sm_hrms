import { useState, useMemo } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { Building2, Eye, EyeOff } from 'lucide-react';
import { useAuth } from '../../core/auth';
import { PendingApprovalError, RegistrationPendingError } from '../../core/auth/api';
import { useSkin } from '../../skins';
import { Button } from '@/components/ui/button';
import PasswordRequirements, { isPasswordValid } from '../../core/components/PasswordRequirements';

type AuthMode = 'signin' | 'signup';

// Public email domains that require explicit organization name
const PUBLIC_EMAIL_DOMAINS = [
  'gmail.com',
  'googlemail.com',
  'outlook.com',
  'hotmail.com',
  'live.com',
  'msn.com',
  'yahoo.com',
  'ymail.com',
  'icloud.com',
  'me.com',
  'mac.com',
  'aol.com',
  'protonmail.com',
  'proton.me',
  'zoho.com',
  'mail.com',
  'gmx.com',
  'fastmail.com',
];

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, register, loginWithGoogle, loginWithMicrosoft, isLoading: authLoading } = useAuth();
  const { skin } = useSkin();

  const [mode, setMode] = useState<AuthMode>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [orgName, setOrgName] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // Get the redirect path from location state or default to home
  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || '/';

  // Detect if the email is from a public domain (requires org name)
  const isPublicEmailDomain = useMemo(() => {
    if (!email || !email.includes('@')) return false;
    const domain = email.split('@')[1]?.toLowerCase();
    return domain && PUBLIC_EMAIL_DOMAINS.includes(domain);
  }, [email]);

  // Show org name field in signup mode when using public email domain
  const showOrgNameField = mode === 'signup' && isPublicEmailDomain;

  const SkinLoginPage = skin.components?.['login-page'];
  if (SkinLoginPage) return <SkinLoginPage />;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      if (mode === 'signup') {
        // Validate signup fields
        if (!fullName.trim()) {
          setError('Please enter your full name');
          setIsLoading(false);
          return;
        }
        // Validate org name if public email domain
        if (showOrgNameField && !orgName.trim()) {
          setError('Please enter an organization name');
          setIsLoading(false);
          return;
        }
        if (!isPasswordValid(password)) {
          setError('Password must be at least 8 characters and include an uppercase letter and a special character');
          setIsLoading(false);
          return;
        }

        // Register with optional org name (for public domains)
        await register(email, password, fullName, showOrgNameField ? orgName : undefined);
      } else {
        await login(email, password);
      }
      navigate(from, { replace: true });
    } catch (err) {
      // Handle pending approval errors with proper navigation
      if (err instanceof PendingApprovalError) {
        navigate('/pending-approval', {
          state: {
            email,
            name: fullName || email.split('@')[0],
            approvalType: 'pending_org_admin',
          },
        });
        return;
      }
      if (err instanceof RegistrationPendingError) {
        navigate('/pending-approval', {
          state: {
            email,
            name: fullName,
            orgName: err.organizationName,
            approvalType: err.approvalType,
            isNewOrg: err.isNewOrganization,
          },
        });
        return;
      }
      setError(err instanceof Error ? err.message : 'Authentication failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleGoogleLogin = async () => {
    setError('');
    try {
      await loginWithGoogle();
    } catch (err) {
      if (err instanceof PendingApprovalError) {
        navigate('/pending-approval', {
          state: {
            email,
            name: fullName || email.split('@')[0],
            approvalType: 'pending_org_admin',
          },
        });
        return;
      }
      if (err instanceof RegistrationPendingError) {
        navigate('/pending-approval', {
          state: {
            email,
            name: fullName,
            orgName: err.organizationName,
            approvalType: err.approvalType,
            isNewOrg: err.isNewOrganization,
          },
        });
        return;
      }
      setError(err instanceof Error ? err.message : 'Google login failed');
    }
  };

  const handleMicrosoftLogin = async () => {
    setError('');
    try {
      await loginWithMicrosoft();
    } catch (err) {
      if (err instanceof PendingApprovalError) {
        navigate('/pending-approval', {
          state: {
            email,
            name: fullName || email.split('@')[0],
            approvalType: 'pending_org_admin',
          },
        });
        return;
      }
      if (err instanceof RegistrationPendingError) {
        navigate('/pending-approval', {
          state: {
            email,
            name: fullName,
            orgName: err.organizationName,
            approvalType: err.approvalType,
            isNewOrg: err.isNewOrganization,
          },
        });
        return;
      }
      setError(err instanceof Error ? err.message : 'Microsoft login failed');
    }
  };

  if (authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-background via-background to-primary/5">
        <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-primary"></div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-background via-background to-primary/5 px-4 py-12 sm:px-6 lg:px-8">
      <div className="w-full max-w-md space-y-8">
        {/* Logo and Title */}
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary">
            <span className="text-white font-bold text-2xl">{skin.branding.logoText}</span>
          </div>
          <h2 className="text-3xl font-bold text-foreground">{skin.branding.name}</h2>
          <p className="mt-2 text-xs text-muted-foreground">
            {skin.branding.releaseDate ? `${skin.branding.releaseDate}. ` : ''}Copyright © {new Date().getFullYear()} {skin.branding.copyrightOwner}.
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            {mode === 'signin' ? 'Sign in to your account' : 'Create a new account'}
          </p>
        </div>

        {/* Login/Signup Form */}
        <div className="rounded-2xl border border-border bg-card px-6 py-8 shadow-sm">
          {/* Mode Toggle */}
          <div className="mb-6 grid grid-cols-2 rounded-xl bg-muted p-1 gap-1">
            <button
              type="button"
              onClick={() => { setMode('signin'); setShowPassword(false); }}
              className={`py-2 text-sm font-medium rounded-lg transition-all outline-none focus-visible:ring-2 focus-visible:ring-ring/40 ${
                mode === 'signin'
                  ? 'bg-card text-foreground shadow-sm'
                  : 'bg-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              Sign In
            </button>
            <button
              type="button"
              onClick={() => { setMode('signup'); setShowPassword(false); }}
              className={`py-2 text-sm font-medium rounded-lg transition-all outline-none focus-visible:ring-2 focus-visible:ring-ring/40 ${
                mode === 'signup'
                  ? 'bg-card text-foreground shadow-sm'
                  : 'bg-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              Sign Up
            </button>
          </div>

          <form className="space-y-6" onSubmit={handleSubmit}>
            {error && (
              <div className="rounded-lg border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                {error}
              </div>
            )}

            {mode === 'signup' && (
              <div>
                <label htmlFor="fullName" className="block text-sm font-medium text-foreground">
                  Full name
                </label>
                <input
                  id="fullName"
                  name="fullName"
                  type="text"
                  autoComplete="name"
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="mt-1 block w-full px-4 py-3 border border-border rounded-xl shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-cobalt focus:border-transparent"
                  placeholder="John Doe"
                />
              </div>
            )}

            <div>
              <label htmlFor="email" className="block text-sm font-medium text-foreground">
                Email address
              </label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 block w-full px-4 py-3 border border-border rounded-xl shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-cobalt focus:border-transparent"
                placeholder="you@example.com"
              />
            </div>

            {/* Organization name field - shown for public email domains */}
            {showOrgNameField && (
              <div className="animate-in slide-in-from-top-2">
                <div className="p-3 bg-warning-subtle border border-warning/30 rounded-xl mb-3">
                  <div className="flex items-start gap-2">
                    <Building2 className="w-4 h-4 text-warning mt-0.5 flex-shrink-0" />
                    <p className="text-xs text-warning">
                      Personal email detected. Please provide your organization name to create a new workspace.
                    </p>
                  </div>
                </div>
                <label htmlFor="orgName" className="block text-sm font-medium text-foreground">
                  Organization name
                </label>
                <input
                  id="orgName"
                  name="orgName"
                  type="text"
                  required
                  value={orgName}
                  onChange={(e) => setOrgName(e.target.value)}
                  className="mt-1 block w-full px-4 py-3 border border-border rounded-xl shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-cobalt focus:border-transparent"
                  placeholder="Acme Inc."
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Your organization request will be reviewed by a platform administrator
                </p>
              </div>
            )}

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-foreground">
                Password
              </label>
              <div className="relative mt-1">
                <input
                  id="password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="block w-full px-4 py-3 pr-10 border border-border rounded-xl shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-cobalt focus:border-transparent"
                  placeholder={mode === 'signin' ? 'Enter your password' : 'Create a password'}
                />
                <button
                  type="button"
                  tabIndex={-1}
                  onClick={() => setShowPassword(p => !p)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 inline-flex h-8 w-8 items-center justify-center rounded-lg bg-transparent text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {mode === 'signup' && <PasswordRequirements password={password} />}
            </div>
            {mode === 'signin' && (
              <div className="mt-1 flex justify-end">
                <Link to="/forgot-password" className="text-sm text-cobalt hover:underline">
                  Forgot password?
                </Link>
              </div>
            )}

            <Button
              type="submit"
              variant="primary"
              size="lg"
              rounded="full"
              fullWidth
              disabled={isLoading}
              loading={isLoading}
              className="shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-cobalt"
            >
              {mode === 'signin' ? 'Sign in' : showOrgNameField ? 'Request Organization' : 'Create account'}
            </Button>
          </form>

          {/* Divider */}
          <div className="mt-6">
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-border" />
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-2 bg-card text-muted-foreground">Or continue with</span>
              </div>
            </div>
          </div>

          {/* Google Sign In */}
          <div className="mt-6">
            <Button
              type="button"
              variant="secondary"
              size="lg"
              rounded="full"
              fullWidth
              onClick={handleGoogleLogin}
              className="gap-3 shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-cobalt"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24">
                <path
                  fill="#4285F4"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                />
                <path
                  fill="#EA4335"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                />
              </svg>
              {mode === 'signin' ? 'Sign in with Google' : 'Sign up with Google'}
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="lg"
              rounded="full"
              fullWidth
              onClick={handleMicrosoftLogin}
              className="mt-3 gap-3 shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-cobalt"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24" aria-hidden="true">
                <path fill="#F25022" d="M2 2h9.5v9.5H2z" />
                <path fill="#7FBA00" d="M12.5 2H22v9.5h-9.5z" />
                <path fill="#00A4EF" d="M2 12.5h9.5V22H2z" />
                <path fill="#FFB900" d="M12.5 12.5H22V22h-9.5z" />
              </svg>
              {mode === 'signin' ? 'Sign in with Microsoft' : 'Sign up with Microsoft'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
