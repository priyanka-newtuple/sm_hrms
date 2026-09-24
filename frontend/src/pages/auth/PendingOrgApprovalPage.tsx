import { useNavigate, useLocation } from 'react-router-dom';
import { Building2, ArrowLeft, Clock } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface PendingOrgApprovalState {
  email?: string;
  name?: string;
  orgName?: string;
  orgId?: string;
}

export default function PendingOrgApprovalPage() {
  const navigate = useNavigate();
  const location = useLocation();

  const state = location.state as PendingOrgApprovalState | undefined;

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-background via-background to-primary/5 px-4 py-12 sm:px-6 lg:px-8">
      <div className="w-full max-w-md space-y-8">
        {/* Logo and Title */}
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-primary/20 to-sky-500/20">
            <Building2 className="h-8 w-8 text-primary" />
          </div>
          <h2 className="text-3xl font-bold text-foreground">Organization Requested</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Your organization request has been submitted
          </p>
        </div>

        {/* Info Card */}
        <div className="rounded-2xl border border-border bg-card px-6 py-8 shadow-sm">
          {/* Organization Info */}
          {state?.orgName && (
            <div className="mb-6 rounded-xl border border-primary/10 bg-gradient-to-r from-primary/5 to-sky-500/5 p-4">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-primary/10 p-2">
                  <Building2 className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">{state.orgName}</p>
                  <p className="text-xs text-muted-foreground">New organization request</p>
                </div>
              </div>
            </div>
          )}

          <div className="text-center mb-6">
            <div className="mb-4 rounded-xl bg-warning-subtle p-4">
              <div className="mb-2 flex items-center justify-center gap-2 text-warning">
                <Clock className="w-5 h-5" />
                <span className="font-medium">Pending Approval</span>
              </div>
              <p className="text-sm text-foreground/85">
                A platform administrator will review your organization request.
                {state?.name && (
                  <span className="mt-2 block text-muted-foreground">
                    Welcome, <strong>{state.name}</strong>!
                  </span>
                )}
              </p>
            </div>
            <p className="text-sm text-muted-foreground">
              Once approved, you'll receive an email notification and can sign in as the organization administrator.
            </p>
          </div>

          {/* What happens next */}
          <div className="border-t border-border pt-6">
            <h3 className="mb-4 text-sm font-medium text-foreground">What happens next?</h3>
            <div className="space-y-3">
              <div className="flex items-start gap-3">
                <div className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-primary/10">
                  <span className="text-xs font-medium text-primary">1</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  Platform administrators are notified of your request
                </p>
              </div>
              <div className="flex items-start gap-3">
                <div className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-primary/10">
                  <span className="text-xs font-medium text-primary">2</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  Your request is reviewed and approved
                </p>
              </div>
              <div className="flex items-start gap-3">
                <div className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-primary/10">
                  <span className="text-xs font-medium text-primary">3</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  You become the admin of your new organization
                </p>
              </div>
            </div>
          </div>

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
          If you have questions, please contact the platform administrator.
        </p>
      </div>
    </div>
  );
}
