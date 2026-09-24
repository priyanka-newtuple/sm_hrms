import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Clock, Mail, ArrowLeft, CheckCircle, Building2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useSkin } from '../../skins';

type ApprovalType = 'pending_org_admin' | 'pending_platform';

interface PendingApprovalState {
  email?: string;
  name?: string;
  orgName?: string;
  approvalType?: ApprovalType;
  isNewOrg?: boolean;
}

export default function PendingApprovalPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { skin } = useSkin();

  const state = location.state as PendingApprovalState | undefined;
  const [password, setPassword] = useState('');
  const [isReminding, setIsReminding] = useState(false);
  const [reminderSent, setReminderSent] = useState(false);
  const [error, setError] = useState('');

  const SkinPendingApproval = skin.components?.['pending-approval'];
  if (SkinPendingApproval) {
    return (
      <SkinPendingApproval
        email={state?.email}
        name={state?.name}
        orgName={state?.orgName}
        approvalType={state?.approvalType}
        isNewOrg={state?.isNewOrg}
        onBack={() => navigate('/login')}
      />
    );
  }

  const handleRemindAdmin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!state?.email || !password) {
      setError('Please enter your password');
      return;
    }

    setError('');
    setIsReminding(true);

    try {
      const response = await fetch('/api/auth/remind-admin', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email: state.email,
          password: password,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to send reminder');
      }

      setReminderSent(true);
      setPassword('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send reminder');
    } finally {
      setIsReminding(false);
    }
  };

  // Determine the approval type for different messaging
  const approvalType = state?.approvalType || 'pending_org_admin';
  const isPlatformApproval = approvalType === 'pending_platform';

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-background via-background to-primary/5 px-4 py-12 sm:px-6 lg:px-8">
      <div className="w-full max-w-md space-y-8">
        {/* Logo and Title */}
        <div className="text-center">
          <div className={`mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl ${isPlatformApproval ? 'bg-primary/10 text-primary' : 'bg-warning-subtle text-warning'}`}>
            {isPlatformApproval ? (
              <Building2 className="h-8 w-8" />
            ) : (
              <Clock className="h-8 w-8" />
            )}
          </div>
          <h2 className="text-3xl font-bold text-foreground">
            {isPlatformApproval ? 'Organization Request Submitted' : 'Pending Approval'}
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            {isPlatformApproval
              ? 'Your organization request is being reviewed'
              : 'Your account request has been submitted'}
          </p>
        </div>

        {/* Info Card */}
        <div className="rounded-2xl border border-border bg-card px-6 py-8 shadow-sm">
          <div className="text-center mb-6">
            {/* Organization info for platform approval */}
            {isPlatformApproval && state?.orgName && (
              <div className="mb-4 rounded-xl border border-primary/10 bg-primary/5 p-4">
                <div className="mb-2 flex items-center justify-center gap-2 text-primary">
                  <Building2 className="w-5 h-5" />
                  <span className="font-semibold">{state.orgName}</span>
                </div>
                <span className="inline-flex items-center rounded-full bg-warning-subtle px-2.5 py-0.5 text-xs font-medium text-warning">
                  Pending Platform Approval
                </span>
              </div>
            )}

            <div className="mb-4 rounded-xl bg-primary/5 p-4">
              <p className="text-foreground/85">
                {isPlatformApproval ? (
                  <>
                    A platform administrator has been notified of your organization request.
                    Once approved, you will become the admin of <strong>{state?.orgName}</strong>.
                  </>
                ) : (
                  <>
                    Your organization administrator has been notified of your registration request.
                  </>
                )}
                {state?.name && (
                  <span className="mt-2 block text-muted-foreground">
                    Welcome, <strong>{state.name}</strong>!
                  </span>
                )}
              </p>
            </div>

            {/* What happens next section for platform approval */}
            {isPlatformApproval && (
              <div className="mb-4 rounded-xl bg-muted/60 p-4 text-left">
                <p className="mb-3 text-sm font-medium text-foreground/85">What happens next?</p>
                <ol className="space-y-2 text-sm text-muted-foreground">
                  <li className="flex items-start gap-2">
                    <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-medium text-primary">1</span>
                    <span>Platform administrators review your request</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-medium text-primary">2</span>
                    <span>Your organization is approved and created</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-medium text-primary">3</span>
                    <span>You become the organization admin</span>
                  </li>
                </ol>
              </div>
            )}

            <p className="text-sm text-muted-foreground">
              Please wait for approval. You will be able to sign in once{' '}
              {isPlatformApproval ? 'your organization is activated' : 'your account is activated'}.
            </p>
          </div>

          {/* Reminder Section - only show for org admin approval */}
          {state?.email && !isPlatformApproval && (
            <div className="border-t border-border pt-6">
              <p className="mb-4 text-center text-sm text-muted-foreground">
                Haven't heard back? Send a reminder to your administrator.
              </p>

              {reminderSent ? (
                <div className="flex items-center justify-center gap-2 text-success bg-success-subtle rounded-xl p-4">
                  <CheckCircle className="w-5 h-5" />
                  <span className="text-sm font-medium">Reminder sent successfully!</span>
                </div>
              ) : (
                <form onSubmit={handleRemindAdmin} className="space-y-4">
                  {error && (
                    <div className="rounded-lg border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                      {error}
                    </div>
                  )}

                  <div>
                    <label htmlFor="password" className="block text-sm font-medium text-foreground">
                      Enter your password to confirm
                    </label>
                    <input
                      id="password"
                      name="password"
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="mt-1 block w-full rounded-xl border border-input bg-background px-4 py-3 shadow-sm placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
                      placeholder="Enter your password"
                    />
                  </div>

                  <Button
                    type="submit"
                    variant="warning"
                    size="lg"
                    rounded="full"
                    fullWidth
                    disabled={isReminding || !password}
                    className="shadow-sm focus:outline-none focus:ring-2 focus:ring-warning/40 focus:ring-offset-2"
                  >
                    {isReminding ? (
                      <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                    ) : (
                      <>
                        <Mail className="w-4 h-4" />
                        Remind Administrator
                      </>
                    )}
                  </Button>
                </form>
              )}
            </div>
          )}

          {/* Back to Login */}
          <div className="mt-6 border-t border-border pt-6">
            <Button
              variant="secondary"
              size="lg"
              rounded="full"
              fullWidth
              onClick={() => navigate('/login')}
              className="focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-ring/30"
              icon={<ArrowLeft className="w-4 h-4" />}
            >
              Back to Sign In
            </Button>
          </div>
        </div>

        {/* Footer */}
        <p className="text-center text-xs text-muted-foreground">
          {isPlatformApproval
            ? 'If you have questions, please contact the platform administrator.'
            : 'If you believe this is an error, please contact your organization administrator.'}
        </p>
      </div>
    </div>
  );
}
