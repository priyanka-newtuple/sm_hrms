/**
 * CalendarIntegrationCard
 *
 * Component for managing Google Calendar integration.
 * Handles OAuth flow via popup and displays connection status.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Loader2,
  AlertCircle,
  Calendar,
  Check,
  X,
  Trash2,
  ExternalLink,
  RefreshCw,
} from 'lucide-react';
import { integrations } from '../../../../core/services/api';
import type { UserIntegration } from '../../../../core/types';
import Modal from '../../../../core/components/Modal';
import { Button } from '@/components/ui/button';
import Badge from '../../../../core/components/Badge';

interface CalendarIntegrationCardProps {
  onRefresh?: () => void;
}

export default function CalendarIntegrationCard({ onRefresh }: CalendarIntegrationCardProps) {
  const [integration, setIntegration] = useState<UserIntegration | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);

  // Disconnect confirmation state
  const [showDisconnectModal, setShowDisconnectModal] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);

  const fetchIntegration = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await integrations.list();
      const googleCalendar = result.integrations.find(
        (item) => item.provider === 'google_calendar'
      );
      setIntegration(googleCalendar || null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load integrations');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchIntegration();
  }, [fetchIntegration]);

  // Listen for OAuth callback messages from popup
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      // Verify origin is same as current page
      if (event.origin !== window.location.origin) return;

      if (event.data?.type === 'google-calendar-callback') {
        if (event.data.success) {
          // Refresh integration status
          fetchIntegration();
          onRefresh?.();
        } else if (event.data.error) {
          setError(event.data.error);
        }
        setConnecting(false);
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [fetchIntegration, onRefresh]);

  const handleConnect = async () => {
    try {
      setConnecting(true);
      setError(null);

      // Get the OAuth URL
      const { auth_url } = await integrations.getGoogleCalendarAuthUrl();

      // Open popup for OAuth
      const width = 600;
      const height = 700;
      const left = window.screenX + (window.outerWidth - width) / 2;
      const top = window.screenY + (window.outerHeight - height) / 2;

      const popup = window.open(
        auth_url,
        'google-calendar-oauth',
        `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`
      );

      // Check if popup was blocked
      if (!popup) {
        setError('Popup blocked. Please allow popups for this site and try again.');
        setConnecting(false);
        return;
      }

      // Monitor popup closing without completing OAuth
      const checkClosed = setInterval(() => {
        if (popup.closed) {
          clearInterval(checkClosed);
          // Only set connecting to false if we haven't received a success message
          setTimeout(() => {
            setConnecting(false);
          }, 1000);
        }
      }, 500);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start OAuth flow');
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    try {
      setDisconnecting(true);
      await integrations.disconnect('google_calendar');
      setIntegration(null);
      setShowDisconnectModal(false);
      onRefresh?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to disconnect');
    } finally {
      setDisconnecting(false);
    }
  };

  const isConnected = integration?.status === 'connected';

  return (
    <>
      <div className="bg-card rounded-xl border border-border p-5 hover:border-border transition-colors">
        {/* Header */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-info rounded-lg flex items-center justify-center">
              <Calendar className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="font-medium text-foreground">Google Calendar</h3>
              <p className="text-xs text-muted-foreground">
                Send interview invites directly to calendars
              </p>
            </div>
          </div>
        </div>

        {/* Loading State */}
        {loading ? (
          <div className="flex items-center justify-center py-4">
            <Loader2 className="w-5 h-5 text-cobalt animate-spin" />
          </div>
        ) : (
          <>
            {/* Status */}
            <div className="flex items-center gap-2 mb-3">
              {isConnected ? (
                <Badge variant="success">
                  <Check className="w-3 h-3 mr-1" />
                  Connected
                </Badge>
              ) : (
                <Badge variant="warning">
                  <X className="w-3 h-3 mr-1" />
                  Not Connected
                </Badge>
              )}
            </div>

            {/* Connected Info */}
            {isConnected && integration && (
              <div className="text-xs text-muted-foreground mb-3 space-y-1">
                {integration.provider_email && (
                  <p>Account: {integration.provider_email}</p>
                )}
                {integration.connected_at && (
                  <p>
                    Connected:{' '}
                    {new Date(integration.connected_at).toLocaleDateString()}
                  </p>
                )}
                {integration.last_used_at && (
                  <p>
                    Last used:{' '}
                    {new Date(integration.last_used_at).toLocaleDateString()}
                  </p>
                )}
              </div>
            )}

            {/* Error State */}
            {(error || integration?.last_error) && (
              <div className="flex items-start gap-2 mb-3 p-2 bg-destructive-subtle rounded-lg">
                <AlertCircle className="w-4 h-4 text-destructive flex-shrink-0 mt-0.5" />
                <p className="text-xs text-destructive">
                  {error || integration?.last_error}
                </p>
              </div>
            )}

            {/* Expired/Revoked State */}
            {integration?.status === 'expired' && (
              <div className="flex items-start gap-2 mb-3 p-2 bg-warning-subtle rounded-lg">
                <AlertCircle className="w-4 h-4 text-warning flex-shrink-0 mt-0.5" />
                <p className="text-xs text-warning">
                  Your authorization has expired. Please reconnect.
                </p>
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center gap-2">
              {isConnected ? (
                <>
                  <Button variant="primary"
                    onClick={handleConnect}
                    disabled={connecting}
                    className="flex-1 px-3 py-2 text-sm font-medium text-cobalt bg-cobalt/10 rounded-lg hover:bg-cobalt/20 transition-colors disabled:opacity-50"
                  >
                    {connecting ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin inline mr-2" />
                        Reconnecting...
                      </>
                    ) : (
                      <>
                        <RefreshCw className="w-4 h-4 inline mr-2" />
                        Reconnect
                      </>
                    )}
                  </Button>
                  <Button variant="ghost-danger" size="icon" onClick={() => setShowDisconnectModal(true)} title="Disconnect">
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </>
              ) : (
                <Button variant="primary"
                  onClick={handleConnect}
                  disabled={connecting}
                  className="flex-1 px-3 py-2 text-sm font-medium text-white bg-cobalt rounded-lg hover:bg-cobalt-dark transition-colors disabled:opacity-50"
                >
                  {connecting ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin inline mr-2" />
                      Connecting...
                    </>
                  ) : (
                    'Connect Google Calendar'
                  )}
                </Button>
              )}
              <a
                href="https://calendar.google.com"
                target="_blank"
                rel="noopener noreferrer"
                className="p-2 text-muted-foreground hover:text-cobalt hover:bg-muted rounded-lg transition-colors"
                title="Open Google Calendar"
              >
                <ExternalLink className="w-4 h-4" />
              </a>
            </div>

            {/* Info Text */}
            {!isConnected && (
              <p className="text-xs text-muted-foreground mt-3">
                Connect your Google Calendar to automatically create calendar
                invites for interviews. Without this, invites will be sent as
                email attachments.
              </p>
            )}
          </>
        )}
      </div>

      {/* Disconnect Confirmation Modal */}
      <Modal
        open={showDisconnectModal}
        onClose={() => setShowDisconnectModal(false)}
        title="Disconnect Google Calendar"
        size="sm"
      >
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Are you sure you want to disconnect Google Calendar? Calendar invites
            will be sent as email attachments instead of being added directly to
            calendars.
          </p>
          <div className="flex justify-end gap-3">
            <Button variant="ghost" onClick={() => setShowDisconnectModal(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={handleDisconnect}
              disabled={disconnecting}
              loading={disconnecting}
            >
              {disconnecting ? 'Disconnecting...' : 'Disconnect'}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}
