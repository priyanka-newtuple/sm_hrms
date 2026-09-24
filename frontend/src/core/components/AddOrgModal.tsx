import { useEffect } from 'react';
import { Loader2, UserPlus } from 'lucide-react';
import FormDialog from './FormDialog';
import Input, { Select } from './Input';
import AlertBanner from './AlertBanner';
import { Button } from '@/components/ui/button';
import { useAddOrg } from '../hooks/useAddOrg';
import { useRoles } from '../hooks/useRoles';

type Props = {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
};

export function AddOrgModal({ open, onClose, onCreated }: Props) {
  const org = useAddOrg();
  const { roles, loading: rolesLoading } = useRoles();

  const roleOptions = [...roles]
    .filter((r) => r.name !== 'superadmin')
    .sort((a, b) => b.priority - a.priority)
    .map((r) => ({ value: r.name, label: r.display_name }));

  // Sync default role once options load
  useEffect(() => {
    if (roleOptions.length > 0 && !org.memberRole) {
      org.setMemberRole(roleOptions[0].value);
    }
  }, [roleOptions, org.memberRole, org.setMemberRole]);

  // Reset state when modal closes
  useEffect(() => {
    if (!open) org.reset();
  }, [open, org.reset]);

  const handleClose = () => {
    if (org.step === 2) onCreated();
    onClose();
  };

  const handleFinish = () => {
    onCreated();
    onClose();
  };

  return (
    <FormDialog
      open={open}
      onClose={handleClose}
      title={org.step === 1 ? 'Add Organization' : 'Invite Members'}
      subtitle={`Step ${org.step} of 2`}
      size="md"
      footer={
        org.step === 1 ? (
          <div className="flex justify-end gap-3">
            <Button variant="ghost" size="md" onClick={handleClose}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="md"
              type="submit"
              form="add-org-form"
              disabled={org.submitting || !org.name.trim()}
            >
              {org.submitting && <Loader2 className="w-4 h-4 animate-spin" />}
              Create & Continue
            </Button>
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">
              {org.members.length > 0
                ? `${org.members.length} member${org.members.length !== 1 ? 's' : ''} added`
                : 'No members added yet'}
            </span>
            <div className="flex gap-3">
              <Button variant="ghost" size="md" onClick={handleFinish}>
                Skip
              </Button>
              <Button variant="primary" size="md" onClick={handleFinish}>
                Done
              </Button>
            </div>
          </div>
        )
      }
    >
      {org.step === 1 ? (
        <form id="add-org-form" onSubmit={org.handleCreateOrg} className="space-y-4">
          {org.error && <AlertBanner tone="error" size="sm">{org.error}</AlertBanner>}
          <Input
            id="org-name"
            label="Organization Name"
            value={org.name}
            onChange={(e) => org.setName(e.target.value)}
            placeholder="Acme Corp"
            required
            autoFocus
          />
          <Input
            id="org-slug"
            label="Slug"
            helperText="Optional — auto-derived from name if blank"
            value={org.slug}
            onChange={(e) => org.setSlug(e.target.value)}
            placeholder="acme-corp"
          />
        </form>
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Add members to <span className="font-medium text-foreground">{org.name}</span>.
            You can skip this step and add them later.
          </p>

          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Input
                id="member-email"
                type="email"
                label="Email"
                value={org.memberEmail}
                onChange={(e) => org.setMemberEmail(e.target.value)}
                placeholder="email@company.com"
              />
              <Input
                id="member-name"
                label="Full Name"
                value={org.memberName}
                onChange={(e) => org.setMemberName(e.target.value)}
                placeholder="Jane Smith"
              />
            </div>
            <div className="flex items-end gap-3">
              <Select
                id="member-role"
                label="Role"
                value={org.memberRole}
                onChange={(e) => org.setMemberRole(e.target.value)}
                disabled={rolesLoading}
                options={
                  rolesLoading
                    ? [{ value: '', label: 'Loading roles…' }]
                    : roleOptions
                }
              />
              <Button
                variant="outline"
                size="md"
                onClick={org.handleAddMember}
                disabled={org.addingMember || !org.memberEmail.trim() || !org.memberName.trim()}
                className="shrink-0 mb-0.5"
              >
                {org.addingMember
                  ? <Loader2 className="w-4 h-4 animate-spin" />
                  : <UserPlus className="w-4 h-4" />}
                Add
              </Button>
            </div>
            {org.memberError && (
              <AlertBanner tone="error" size="sm">{org.memberError}</AlertBanner>
            )}
          </div>

          {org.members.length > 0 && (
            <div className="space-y-1.5 max-h-40 overflow-y-auto">
              {org.members.map((m) => (
                <div
                  key={m.email}
                  className="flex items-center justify-between px-3 py-2 bg-muted rounded-lg text-sm"
                >
                  <div>
                    <span className="font-medium">{m.full_name}</span>
                    <span className="text-muted-foreground ml-2">{m.email}</span>
                  </div>
                  <span className="text-xs text-muted-foreground capitalize">
                    {m.role.replace('_', ' ')}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </FormDialog>
  );
}

export default AddOrgModal;
