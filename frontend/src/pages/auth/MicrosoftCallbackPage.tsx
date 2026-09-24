import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../core/auth';
import { PendingApprovalError, RegistrationPendingError } from '../../core/auth/api';
import { useSkin } from '../../skins';
import { Button } from '@/components/ui/button';

const MS_OAUTH_STATE_KEY = 'ats_ms_oauth_state';

export default function MicrosoftCallbackPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { handleMicrosoftCallback } = useAuth();
  const { skin } = useSkin();
  const [error, setError] = useState<string | null>(null);
  const hasProcessed = useRef(false);
  const SkinCallbackUI = skin.components?.['microsoft-callback'];

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const code = searchParams.get('code');
    const state = searchParams.get('state') || sessionStorage.getItem(MS_OAUTH_STATE_KEY);
    const errorParam = searchParams.get('error');

    // Strip the one-time code/state from the URL immediately. The login code and
    // its PKCE verifier are single-use, so a refresh, back-button, or restored tab
    // must not be able to replay this callback (which would fail with
    // "missing/expired PKCE verifier"). We've already captured the values above.
    window.history.replaceState({}, document.title, window.location.pathname);

    if (errorParam) {
      setError(`Microsoft authentication failed: ${errorParam}`);
      return;
    }

    // No code/state means this isn't an in-progress login (e.g. a stale or direct
    // visit) — send the user to sign in rather than showing an error.
    if (!code || !state) {
      navigate('/login', { replace: true });
      return;
    }

    handleMicrosoftCallback(code, state)
      .then(() => {
        sessionStorage.removeItem(MS_OAUTH_STATE_KEY);
        navigate('/', { replace: true });
      })
      .catch((err) => {
        sessionStorage.removeItem(MS_OAUTH_STATE_KEY);
        if (err instanceof RegistrationPendingError) {
          navigate('/pending-approval', {
            state: {
              email: '',
              name: '',
              orgName: err.organizationName,
              approvalType: err.approvalType,
              isNewOrg: err.isNewOrganization,
            },
          });
          return;
        }
        if (err instanceof PendingApprovalError) {
          navigate('/pending-approval', {
            state: {
              approvalType: 'pending_org_admin',
            },
          });
          return;
        }
        // Most failures here are an expired or already-used sign-in link
        // (e.g. a replayed callback). Show a friendly, actionable message
        // rather than a raw error; the action is always "sign in again".
        setError('Your sign-in link expired or was already used. Please sign in again.');
      });
  }, [searchParams, handleMicrosoftCallback, navigate]);

  if (SkinCallbackUI) {
    return (
      <SkinCallbackUI
        status={error ? 'error' : 'working'}
        errorMessage={error}
        onRetry={() => navigate('/login')}
      />
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-muted/50">
        <div className="max-w-md w-full bg-card p-8 rounded-2xl shadow-sm">
          <div className="text-center">
            <div className="mx-auto w-12 h-12 bg-destructive-subtle rounded-full flex items-center justify-center mb-4">
              <svg className="w-6 h-6 text-destructive" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h2 className="text-xl font-semibold text-foreground mb-2">Authentication Failed</h2>
            <p className="text-muted-foreground mb-6">{error}</p>
            <Button
              variant="primary"
              rounded="full"
              onClick={() => navigate('/login')}
              className="shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-cobalt"
            >
              Back to Login
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/50">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-cobalt mx-auto mb-4"></div>
        <p className="text-muted-foreground">Completing Microsoft sign in...</p>
      </div>
    </div>
  );
}
