/**
 * GoogleCalendarCallbackPage
 *
 * Handles the OAuth callback from Google Calendar authorization.
 * This page runs in a popup and communicates back to the parent window.
 */

import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Loader2, CheckCircle, XCircle } from 'lucide-react';
import { integrations } from '../core/services/api';
import { Button } from '@/components/ui/button';

type CallbackStatus = 'processing' | 'success' | 'error';

export default function GoogleCalendarCallbackPage() {
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState<CallbackStatus>('processing');
  const [message, setMessage] = useState('Connecting Google Calendar...');

  useEffect(() => {
    const handleCallback = async () => {
      const code = searchParams.get('code');
      const state = searchParams.get('state');
      const errorParam = searchParams.get('error');

      // Handle OAuth errors
      if (errorParam) {
        const errorDescription = searchParams.get('error_description') || errorParam;
        setStatus('error');
        setMessage(
          errorParam === 'access_denied'
            ? 'Authorization was cancelled.'
            : `Google authorization failed: ${errorDescription}`
        );

        // Notify parent window
        if (window.opener) {
          window.opener.postMessage(
            {
              type: 'google-calendar-callback',
              success: false,
              error: errorDescription,
            },
            window.location.origin
          );
        }
        return;
      }

      // Validate required params
      if (!code || !state) {
        setStatus('error');
        setMessage('Invalid callback: missing authorization code or state');

        if (window.opener) {
          window.opener.postMessage(
            {
              type: 'google-calendar-callback',
              success: false,
              error: 'Invalid callback parameters',
            },
            window.location.origin
          );
        }
        return;
      }

      try {
        // Exchange code for tokens
        const result = await integrations.googleCalendarCallback({ code, state });

        if (result.success) {
          setStatus('success');
          setMessage('Google Calendar connected successfully!');

          // Notify parent window
          if (window.opener) {
            window.opener.postMessage(
              {
                type: 'google-calendar-callback',
                success: true,
                integration: result.integration,
              },
              window.location.origin
            );
          }

          // Auto-close popup after success
          setTimeout(() => {
            window.close();
          }, 1500);
        } else {
          setStatus('error');
          setMessage(result.message || 'Failed to connect Google Calendar');

          if (window.opener) {
            window.opener.postMessage(
              {
                type: 'google-calendar-callback',
                success: false,
                error: result.message,
              },
              window.location.origin
            );
          }
        }
      } catch (e) {
        const errorMessage = e instanceof Error ? e.message : 'Connection failed';
        setStatus('error');
        setMessage(errorMessage);

        if (window.opener) {
          window.opener.postMessage(
            {
              type: 'google-calendar-callback',
              success: false,
              error: errorMessage,
            },
            window.location.origin
          );
        }
      }
    };

    handleCallback();
  }, [searchParams]);

  const handleClose = () => {
    window.close();
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/50">
      <div className="max-w-md w-full bg-card p-8 rounded-2xl shadow-sm text-center">
        {status === 'processing' && (
          <>
            <Loader2 className="w-12 h-12 text-cobalt animate-spin mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-foreground mb-2">
              Connecting...
            </h2>
            <p className="text-muted-foreground">{message}</p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="mx-auto w-12 h-12 bg-success-subtle rounded-full flex items-center justify-center mb-4">
              <CheckCircle className="w-6 h-6 text-success" />
            </div>
            <h2 className="text-xl font-semibold text-foreground mb-2">
              Connected!
            </h2>
            <p className="text-muted-foreground mb-4">{message}</p>
            <p className="text-sm text-muted-foreground">
              This window will close automatically...
            </p>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="mx-auto w-12 h-12 bg-destructive-subtle rounded-full flex items-center justify-center mb-4">
              <XCircle className="w-6 h-6 text-destructive" />
            </div>
            <h2 className="text-xl font-semibold text-foreground mb-2">
              Connection Failed
            </h2>
            <p className="text-muted-foreground mb-6">{message}</p>
            <Button
              variant="primary"
              rounded="full"
              onClick={handleClose}
              className="shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-cobalt"
            >
              Close Window
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
