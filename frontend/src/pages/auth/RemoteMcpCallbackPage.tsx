import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { remoteMcp } from '@/core/services/api';

const CONNECTORS_SETTINGS_PATH = '/settings?tab=connectors';

export default function RemoteMcpCallbackPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const code = searchParams.get('code');
    const state = searchParams.get('state');
    const errorParam = searchParams.get('error');

    // The authorization code and signed state are single-use — strip them from
    // the URL immediately so a refresh or back-button can't replay this callback.
    window.history.replaceState({}, document.title, window.location.pathname);

    if (errorParam) {
      Promise.resolve().then(() => setError('Sign-in took too long, please try again.'));
      return;
    }

    // No code/state means this isn't an in-progress connection (a stale or
    // direct visit) — go back to the list rather than showing an error.
    if (!code || !state) {
      navigate(CONNECTORS_SETTINGS_PATH, { replace: true });
      return;
    }

    remoteMcp
      .oauthCallback(code, state)
      .then(() => navigate(CONNECTORS_SETTINGS_PATH, { replace: true }))
      .catch(() => setError('Authorization failed, please try again.'));
  }, [searchParams, navigate]);

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
            <h2 className="text-xl font-semibold text-foreground mb-2">Connection failed</h2>
            <p className="text-muted-foreground mb-6">{error}</p>
            <Button variant="primary" rounded="full" onClick={() => navigate(CONNECTORS_SETTINGS_PATH)}>
              Back to Connectors
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
        <p className="text-muted-foreground">Finishing connection...</p>
      </div>
    </div>
  );
}
