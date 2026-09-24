import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Loader2, CheckCircle, XCircle, Building2, AlertCircle } from 'lucide-react';
import { invitations } from '../../core/services/api';
import type { InvitationValidation } from '../../core/types';
import { Button } from '@/components/ui/button';
import PasswordRequirements, { isPasswordValid } from '../../core/components/PasswordRequirements';

export default function AcceptInvitePage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');

  const [loading, setLoading] = useState(true);
  const [validation, setValidation] = useState<InvitationValidation | null>(null);
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');

  useEffect(() => {
    const validateToken = async () => {
      if (!token) {
        setValidation({ valid: false, error: 'No invitation token provided' });
        setLoading(false);
        return;
      }

      try {
        const result = await invitations.validate(token);
        setValidation(result);
      } catch (e) {
        setValidation({ valid: false, error: e instanceof Error ? e.message : 'Failed to validate invitation' });
      } finally {
        setLoading(false);
      }
    };

    validateToken();
  }, [token]);

  const isExistingUser = validation?.user_exists === true;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!isExistingUser) {
      if (!fullName.trim()) {
        setError('Please enter your full name');
        return;
      }

      if (!isPasswordValid(password)) {
        setError('Password must be at least 8 characters and include an uppercase letter and a special character');
        return;
      }

      if (password !== confirmPassword) {
        setError('Passwords do not match');
        return;
      }
    }

    try {
      setSubmitting(true);
      const result = await invitations.accept({
        token: token!,
        ...(isExistingUser ? {} : { full_name: fullName.trim(), password }),
      });
      setSuccessMessage(result.already_member ? result.message : '');
      setSuccess(true);
      setTimeout(() => {
        navigate('/login', {
          state: {
            message: isExistingUser
              ? 'Invitation accepted! Sign in with your existing password.'
              : 'Account created! Please sign in.',
          },
        });
      }, 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to accept invitation');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-muted/50 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-8 h-8 text-cobalt animate-spin mx-auto" />
          <p className="mt-4 text-muted-foreground">Validating invitation...</p>
        </div>
      </div>
    );
  }

  if (!validation?.valid) {
    return (
      <div className="min-h-screen bg-muted/50 flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-card rounded-2xl shadow-lg p-8 text-center">
          <div className="w-16 h-16 bg-destructive-subtle rounded-full flex items-center justify-center mx-auto mb-4">
            <XCircle className="w-8 h-8 text-destructive" />
          </div>
          <h1 className="text-xl font-semibold text-foreground mb-2">Invalid Invitation</h1>
          <p className="text-muted-foreground mb-6">{validation?.error || 'This invitation link is invalid or has expired.'}</p>
          <Button variant="primary" onClick={() => navigate('/login')}>
            Go to Login
          </Button>
        </div>
      </div>
    );
  }

  if (success) {
    return (
      <div className="min-h-screen bg-muted/50 flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-card rounded-2xl shadow-lg p-8 text-center">
          <div className="w-16 h-16 bg-success-subtle rounded-full flex items-center justify-center mx-auto mb-4">
            <CheckCircle className="w-8 h-8 text-success" />
          </div>
          <h1 className="text-xl font-semibold text-foreground mb-2">Welcome!</h1>
          <p className="text-muted-foreground">
            {successMessage
              ? `${successMessage} Redirecting to login...`
              : isExistingUser
              ? `You've joined ${validation?.organization_name ?? 'the organization'}. Redirecting to login...`
              : 'Your account has been created. Redirecting to login...'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-muted/50 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-card rounded-2xl shadow-lg p-8">
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-cobalt/10 rounded-full flex items-center justify-center mx-auto mb-4">
            <Building2 className="w-8 h-8 text-cobalt" />
          </div>
          <h1 className="text-2xl font-semibold text-foreground mb-2">Accept Invitation</h1>
          <p className="text-muted-foreground">
            You've been invited to join <strong>{validation.organization_name}</strong> as a{' '}
            <strong>{validation.role?.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}</strong>.
          </p>
          {isExistingUser && (
            <p className="mt-3 text-sm text-muted-foreground">
              You already have an account. Keep signing in with your existing password.
            </p>
          )}
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="bg-destructive-subtle border border-destructive/30 rounded-lg p-3 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-destructive mt-0.5 flex-shrink-0" />
              <p className="text-sm text-destructive">{error}</p>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Email</label>
            <input
              type="email"
              value={validation.email || ''}
              disabled
              className="w-full px-3 py-2 border border-border rounded-lg bg-muted/50 text-muted-foreground"
            />
          </div>

          {!isExistingUser && (
            <>
              <div>
                <label htmlFor="full-name" className="block text-sm font-medium text-foreground mb-1">
                  Full Name
                </label>
                <input
                  id="full-name"
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Enter your full name"
                  disabled={submitting}
                  className="w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-cobalt focus:border-cobalt disabled:bg-muted"
                  autoFocus
                />
              </div>

              <div>
                <label htmlFor="password" className="block text-sm font-medium text-foreground mb-1">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Create a password"
                  disabled={submitting}
                  className="w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-cobalt focus:border-cobalt disabled:bg-muted"
                />
                <PasswordRequirements password={password} />
              </div>

              <div>
                <label htmlFor="confirm-password" className="block text-sm font-medium text-foreground mb-1">
                  Confirm Password
                </label>
                <input
                  id="confirm-password"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Confirm your password"
                  disabled={submitting}
                  className="w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-cobalt focus:border-cobalt disabled:bg-muted"
                />
              </div>
            </>
          )}

          <Button variant="primary"
            type="submit"
            size="lg"
            fullWidth
            disabled={submitting}
            loading={submitting}
          >
            {submitting
              ? isExistingUser
                ? 'Joining...'
                : 'Creating Account...'
              : isExistingUser
                ? `Join ${validation.organization_name ?? 'organization'}`
                : 'Accept & Create Account'}
          </Button>
        </form>

        {!isExistingUser && (
          <p className="mt-6 text-center text-sm text-muted-foreground">
            Already have an account?{' '}
            <Button
              variant="link"
              onClick={() => navigate('/login')}
              className="text-cobalt hover:underline font-medium"
            >
              Sign in
            </Button>
          </p>
        )}
      </div>
    </div>
  );
}
