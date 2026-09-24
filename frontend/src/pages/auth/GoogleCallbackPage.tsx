import { useEffect, useState, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../core/auth';
import { RegistrationPendingError, PendingApprovalError } from '../../core/auth/api';
import { Button } from '@/components/ui/button';

export default function GoogleCallbackPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { handleGoogleCallback } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const hasProcessed = useRef(false);

  useEffect(() => {
    // Guard against React StrictMode double-invocation
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const code = searchParams.get('code');
    const errorParam = searchParams.get('error');

    if (errorParam) {
      setError(`Google authentication failed: ${errorParam}`);
      return;
    }

    if (!code) {
      setError('No authorization code received');
      return;
    }

    handleGoogleCallback(code)
      .then(() => {
        navigate('/', { replace: true });
      })
      .catch((err) => {
        // Handle registration pending approval
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
        // Handle existing user pending approval
        if (err instanceof PendingApprovalError) {
          navigate('/pending-approval', {
            state: {
              approvalType: 'pending_org_admin',
            },
          });
          return;
        }
        setError(err instanceof Error ? err.message : 'Authentication failed');
      });
  }, [searchParams, handleGoogleCallback, navigate]);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-muted/50">
        <div className="max-w-md w-full bg-card p-8 rounded-2xl shadow-sm">
          <div className="text-center">
            <div className="mx-auto w-12 h-12 bg-destructive-subtle rounded-full flex items-center justify-center mb-4">
              <svg
                className="w-6 h-6 text-destructive"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </div>
            <h2 className="text-xl font-semibold text-foreground mb-2">
              Authentication Failed
            </h2>
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
        <p className="text-muted-foreground">Completing sign in...</p>
      </div>
    </div>
  );
}
