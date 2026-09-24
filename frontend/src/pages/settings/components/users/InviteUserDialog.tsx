import { useState, useEffect } from 'react';
import { UserPlus } from 'lucide-react';
import {
  AlertBanner,
  Button,
  FormDialog,
  Input,
  Select,
} from '../../../../core/components';
import { invitations } from '../../../../core/services/api';
import { useRoles } from '../../../../core/hooks/useRoles';
import { EMAIL_REGEX } from '../../../../core/utils';

interface InviteUserDialogProps {
  open: boolean;
  onClose: () => void;
  onInvited: () => void;
  canWrite?: boolean;
}

export default function InviteUserDialog({
  open,
  onClose,
  onInvited,
  canWrite = true,
}: InviteUserDialogProps) {
  const { roles: rbacRoles, loading: rolesLoading, error: rolesError } = useRoles();
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<string>('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const roleOptions = [...rbacRoles]
    .sort((a, b) => b.priority - a.priority)
    .map(r => ({ value: r.name, label: r.display_name }));

  // Sync selected role to first available option whenever the list loads
  useEffect(() => {
    if (roleOptions.length > 0 && !role) {
      setRole(roleOptions[0].value);
    }
  }, [roleOptions, role]);

  const resetForm = () => {
    setEmail('');
    setRole('');
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!canWrite) {
      setError('You do not have permission to invite users.');
      return;
    }

    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedEmail) {
      setError('Email is required');
      return;
    }

    if (!EMAIL_REGEX.test(trimmedEmail)) {
      setError('Please enter a valid email address');
      return;
    }

    if (!role) {
      setError('Please select a role');
      return;
    }

    try {
      setSubmitting(true);
      await invitations.create({ email: trimmedEmail, role });
      resetForm();
      onInvited();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to send invitation');
    } finally {
      setSubmitting(false);
    }
  };

  const handleClose = () => {
    if (!submitting) {
      resetForm();
      onClose();
    }
  };

  return (
    <FormDialog
      open={open}
      onClose={handleClose}
      title="Invite User"
      subtitle="Add a teammate and assign their starting access level."
      size="sm"
      footer={
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={handleClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="ghost"
            form="invite-user-form"
            type="submit"
            disabled={!canWrite || submitting}
            loading={submitting}
            icon={<UserPlus className="w-4 h-4" />}
          >
            Send Invitation
          </Button>
        </div>
      }
    >
      <form id="invite-user-form" onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <AlertBanner tone="error" size="sm">
            {error}
          </AlertBanner>
        )}

        {rolesError && (
          <AlertBanner tone="error" size="sm">
            Could not load roles: {rolesError}
          </AlertBanner>
        )}

        <Input
          id="invite-email"
          type="email"
          label="Email address"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="colleague@company.com"
          disabled={!canWrite || submitting}
          autoFocus
        />

        <Select
          id="invite-role"
          label="Role"
          value={role}
          onChange={(e) => setRole(e.target.value)}
          disabled={!canWrite || submitting || rolesLoading || roleOptions.length === 0}
          options={rolesLoading ? [{ value: '', label: 'Loading roles…' }] : roleOptions}
        />
      </form>
    </FormDialog>
  );
}
